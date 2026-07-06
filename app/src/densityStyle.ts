import { colorForValue, type DensityStyle } from './colormaps'

/**
 * Post-traitement appliqué aux textures de densité (L2-L5), calibré
 * visuellement via app/public/glow-test.html. Ne pas modifier ces valeurs
 * sans repasser par cet outil.
 */
export const DENSITY_STYLE_PARAMS = {
  gamma: 1.0,
  soften: 0, // "adoucissement vapeur" — désactivé dans la calibration retenue
  sharpen: 0.15, // netteté des filaments (unsharp mask)
  halo: 0, // bloom — désactivé dans la calibration retenue
  pointIntensity: 0.25,
  pointThreshold: 81.5, // percentile
  pointSize: 1.0, // px, à la résolution de travail (voir n dans processDensityField)
}

function boxBlur(src: Float32Array, w: number, h: number, radius: number): Float32Array {
  if (radius < 0.5) return Float32Array.from(src)
  const r = Math.round(radius)
  const tmp = new Float32Array(w * h)
  const out = new Float32Array(w * h)
  for (let y = 0; y < h; y++) {
    let sum = 0
    let count = 0
    for (let x = -r; x <= r; x++) {
      const xi = Math.min(Math.max(x, 0), w - 1)
      sum += src[y * w + xi]
      count++
    }
    for (let x = 0; x < w; x++) {
      tmp[y * w + x] = sum / count
      const xOut = Math.min(Math.max(x - r, 0), w - 1)
      const xIn = Math.min(Math.max(x + r + 1, 0), w - 1)
      sum += src[y * w + xIn] - src[y * w + xOut]
    }
  }
  for (let x = 0; x < w; x++) {
    let sum = 0
    let count = 0
    for (let y = -r; y <= r; y++) {
      const yi = Math.min(Math.max(y, 0), h - 1)
      sum += tmp[yi * w + x]
      count++
    }
    for (let y = 0; y < h; y++) {
      out[y * w + x] = sum / count
      const yOut = Math.min(Math.max(y - r, 0), h - 1)
      const yIn = Math.min(Math.max(y + r + 1, 0), h - 1)
      sum += tmp[yIn * w + x] - tmp[yOut * w + x]
    }
  }
  return out
}

interface Peak {
  x: number
  y: number
  v: number
}

function detectPeaks(values: Float32Array, w: number, h: number, thresholdPercentile: number, minDistPx: number): Peak[] {
  const sorted = Float32Array.from(values).sort()
  const thresholdVal = sorted[Math.floor((sorted.length * thresholdPercentile) / 100)]
  const candidates: Peak[] = []
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const v = values[y * w + x]
      if (v < thresholdVal) continue
      let isMax = true
      for (let dy = -1; dy <= 1 && isMax; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          if (dx === 0 && dy === 0) continue
          if (values[(y + dy) * w + (x + dx)] > v) {
            isMax = false
            break
          }
        }
      }
      if (isMax) candidates.push({ x, y, v })
    }
  }
  candidates.sort((a, b) => b.v - a.v)
  const selected: Peak[] = []
  for (const c of candidates) {
    let tooClose = false
    for (const s of selected) {
      const d2 = (c.x - s.x) ** 2 + (c.y - s.y) ** 2
      if (d2 < minDistPx * minDistPx) {
        tooClose = true
        break
      }
    }
    if (!tooClose) selected.push(c)
    if (selected.length > 300) break
  }
  return selected
}

/**
 * Applique le pipeline complet (adoucissement -> netteté -> contraste ->
 * halo -> points) à un champ de densité en niveaux de gris (Float32Array,
 * valeurs 0-1, grille n×n) et retourne une ImageData colorisée selon le
 * style choisi.
 */
export function processDensityField(
  grayValues: Float32Array,
  n: number,
  style: DensityStyle,
  params = DENSITY_STYLE_PARAMS
): ImageData {
  let field = params.soften > 0.05 ? boxBlur(grayValues, n, n, params.soften) : Float32Array.from(grayValues)

  if (params.sharpen > 0.01) {
    const blurred = boxBlur(field, n, n, 2.5)
    for (let i = 0; i < field.length; i++) field[i] = field[i] + params.sharpen * (field[i] - blurred[i])
  }

  let vmin = Infinity
  let vmax = -Infinity
  for (let i = 0; i < field.length; i++) {
    if (field[i] < vmin) vmin = field[i]
    if (field[i] > vmax) vmax = field[i]
  }
  const span = vmax - vmin || 1
  const normed = new Float32Array(field.length)
  for (let i = 0; i < field.length; i++) {
    normed[i] = Math.pow(Math.min(Math.max((field[i] - vmin) / span, 0), 1), 1 / params.gamma)
  }

  const canvas = document.createElement('canvas')
  canvas.width = n
  canvas.height = n
  const ctx = canvas.getContext('2d')!
  const out = ctx.createImageData(n, n)
  for (let i = 0; i < normed.length; i++) {
    const [r, g, b] = colorForValue(normed[i], style)
    out.data[i * 4] = r
    out.data[i * 4 + 1] = g
    out.data[i * 4 + 2] = b
    out.data[i * 4 + 3] = 255
  }
  ctx.putImageData(out, 0, 0)

  if (params.halo > 0.02) {
    const bright = new Float32Array(normed.length)
    for (let i = 0; i < normed.length; i++) bright[i] = Math.max(normed[i] - 0.55, 0) * 2.2
    const bloomed = boxBlur(bright, n, n, 6)
    const bloomCanvas = document.createElement('canvas')
    bloomCanvas.width = n
    bloomCanvas.height = n
    const bctx = bloomCanvas.getContext('2d')!
    const bout = bctx.createImageData(n, n)
    for (let i = 0; i < bloomed.length; i++) {
      const v = Math.min(bloomed[i] * params.halo, 1)
      const [r, g, b] = colorForValue(Math.min(normed[i] + v, 1), style)
      bout.data[i * 4] = r
      bout.data[i * 4 + 1] = g
      bout.data[i * 4 + 2] = b
      bout.data[i * 4 + 3] = v * 255
    }
    bctx.putImageData(bout, 0, 0)
    ctx.drawImage(bloomCanvas, 0, 0)
  }

  if (params.pointIntensity > 0.02) {
    const peaks = detectPeaks(normed, n, n, params.pointThreshold, params.pointSize * 1.5)
    for (const p of peaks) {
      const [r, g, b] = colorForValue(1, style)
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, params.pointSize)
      grad.addColorStop(0, `rgba(${r},${g},${b},${Math.min(params.pointIntensity, 1)})`)
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
      ctx.fillStyle = grad
      ctx.beginPath()
      ctx.arc(p.x, p.y, params.pointSize, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  return ctx.getImageData(0, 0, n, n)
}
