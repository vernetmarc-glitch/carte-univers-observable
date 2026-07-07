import { colorForValue, type DensityStyle } from './colormaps'

/**
 * Post-traitement appliqué aux textures de densité (L2-L5), calibré
 * visuellement via app/public/glow-test.html. Ne pas modifier ces valeurs
 * sans repasser par cet outil.
 */
export interface DensityStyleParams {
  gamma: number
  soften: number
  sharpen: number
  sharpenRadius: number // px, à la résolution de travail — contrôle l'échelle de structure mise en valeur
  halo: number
  pointIntensity: number
  pointThreshold: number // percentile
  pointSize: number // px, à la résolution de travail (voir n dans processDensityField)
}

/**
 * Paramètres de style PAR LAYER — volontairement différents d'un layer à
 * l'autre : le contraste réel des structures diffère selon l'échelle (un
 * amas n'a pas le même profil de densité qu'un superamas), et chaque layer
 * a été (ou sera) calibré séparément via glow-test.html.
 *
 * IMPORTANT : ceci était auparavant un objet UNIQUE partagé par tous les
 * layers — chaque nouvelle calibration écrasait la précédente sans que ce
 * soit voulu (cf. discussion du 6 juillet). Toute future calibration doit
 * ajouter/mettre à jour l'entrée du layer concerné ici, jamais remplacer
 * DEFAULT_DENSITY_STYLE_PARAMS globalement.
 */
export const DEFAULT_DENSITY_STYLE_PARAMS: DensityStyleParams = {
  gamma: 0.75,
  soften: 0,
  sharpen: 0,
  sharpenRadius: 2.5,
  halo: 0.1,
  pointIntensity: 0.6,
  pointThreshold: 82,
  pointSize: 1.5,
}

export const DENSITY_STYLE_PARAMS_BY_LAYER: Partial<Record<string, DensityStyleParams>> = {
  // "milkyway" et "realgalaxy" (cf. scripts/generate_simulated_textures.mjs
  // et RealGalaxiesLayer.tsx) : champs de points déjà individualisés
  // (étoiles/nuages d'étoiles), pas des champs de densité continus — la
  // détection de pics + halo de bloom du pipeline standard n'a pas de sens
  // ici (elle est pensée pour repérer des amas dans un champ lisse) et
  // produirait des artefacts. On désactive donc halo/points, et on garde un
  // gamma marqué car les textures sources sont très sombres/éparses par
  // construction (fond à 0 partout sauf les étoiles).
  milkyway: {
    gamma: 0.45,
    soften: 0,
    sharpen: 0,
    sharpenRadius: 2.5,
    halo: 0,
    pointIntensity: 0,
    pointThreshold: 100,
    pointSize: 0,
  },
  realgalaxy: {
    gamma: 0.45,
    soften: 0,
    sharpen: 0,
    sharpenRadius: 2.5,
    halo: 0,
    pointIntensity: 0,
    pointThreshold: 100,
    pointSize: 0,
  },
  // Calibré le 7 juillet via app/public/l1b-anchor-test.html — l1b intègre
  // désormais du bruit "nuages interstellaires" + un flou d'ensemble
  // (cf. generate_layers.py), c'est un vrai champ diffus comme les autres
  // layers de densité, donc le halo/points par défaut s'applique (contraste
  // un peu plus doux que le défaut 0.75).
  l1b: {
    gamma: 0.56,
    soften: 0,
    sharpen: 0,
    sharpenRadius: 2.5,
    halo: 0.1,
    pointIntensity: 0.6,
    pointThreshold: 82,
    pointSize: 1.5,
  },
  // Calibré le 6 juillet via glow-test.html.
  l2: {
    gamma: 0.85,
    soften: 0,
    sharpen: 0,
    sharpenRadius: 2.5,
    halo: 0.25,
    pointIntensity: 0.6,
    pointThreshold: 81.0,
    pointSize: 2.5,
  },
  // Calibré le 6 juillet via glow-test.html.
  l4: {
    gamma: 0.65,
    soften: 0,
    sharpen: 0,
    sharpenRadius: 2.5,
    halo: 0,
    pointIntensity: 1.0,
    pointThreshold: 82.5,
    pointSize: 1.0,
  },
}

/** Renvoie les paramètres calibrés pour ce layer, ou le défaut si pas encore calibré. */
export function getStyleParamsForLayer(layerKey: string): DensityStyleParams {
  return DENSITY_STYLE_PARAMS_BY_LAYER[layerKey] ?? DEFAULT_DENSITY_STYLE_PARAMS
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
  params: DensityStyleParams = DEFAULT_DENSITY_STYLE_PARAMS
): ImageData {
  let field = params.soften > 0.05 ? boxBlur(grayValues, n, n, params.soften) : Float32Array.from(grayValues)

  if (params.sharpen > 0.01) {
    const blurred = boxBlur(field, n, n, params.sharpenRadius)
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
