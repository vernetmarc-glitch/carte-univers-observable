import { useEffect, useRef } from 'react'
import { buildLookupTable, type DensityStyle } from './colormaps'

interface ProceduralLayer {
  key: 'l2' | 'l3' | 'l4' | 'l5'
  maxMpc: number
}

// Du plus petit au plus grand — cf. document d'architecture §4.1 (layer 1, local,
// n'est pas procédural et n'a pas de texture).
const PROCEDURAL_LAYERS: ProceduralLayer[] = [
  { key: 'l2', maxMpc: 30 },
  { key: 'l3', maxMpc: 150 },
  { key: 'l4', maxMpc: 300 },
  { key: 'l5', maxMpc: 14570 },
]

const BOUNDARY_EDGES = [30, 150, 300] // entre l2/l3, l3/l4, l4/l5
const FADE_WIDTH_DEX = 0.15 // largeur de la zone de fondu, en décades (log10)

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(Math.max((x - edge0) / (edge1 - edge0), 0), 1)
  return t * t * (3 - 2 * t)
}

/** Poids de mélange des 4 layers procéduraux pour un champ de vue donné (partition de 1). */
function getLayerWeights(halfWidthMpc: number): Record<string, number> {
  const x = Math.log10(halfWidthMpc)
  const [e23, e34, e45] = BOUNDARY_EDGES.map(Math.log10)
  const w23 = smoothstep(e23 - FADE_WIDTH_DEX, e23 + FADE_WIDTH_DEX, x)
  const w34 = smoothstep(e34 - FADE_WIDTH_DEX, e34 + FADE_WIDTH_DEX, x)
  const w45 = smoothstep(e45 - FADE_WIDTH_DEX, e45 + FADE_WIDTH_DEX, x)
  return {
    l2: 1 - w23,
    l3: w23 * (1 - w34),
    l4: w34 * (1 - w45),
    l5: w45,
  }
}

interface DensityLayerProps {
  style: DensityStyle
  opacity: number
  halfWidthMpc: number
}

/**
 * Couche de densité multi-layers (Phase 4, étape 1).
 *
 * Charge les 4 textures procédurales (générées hors-ligne par
 * scripts/generate_layers.py, avec héritage hiérarchique entre échelles),
 * les recolore selon le style choisi, puis les mélange avec un fondu doux
 * autour de chaque frontière d'échelle en fonction du zoom courant.
 */
export default function DensityLayer({ style, opacity, halfWidthMpc }: DensityLayerProps) {
  const outputCanvasRef = useRef<HTMLCanvasElement>(null)
  const grayDataRef = useRef<Record<string, ImageData>>({})
  const colorizedRef = useRef<Record<string, HTMLCanvasElement>>({})
  const loadedCountRef = useRef(0)

  // Chargement unique des 4 textures sources en niveaux de gris.
  useEffect(() => {
    PROCEDURAL_LAYERS.forEach((layer) => {
      const img = new Image()
      img.src = `${import.meta.env.BASE_URL}data/density_${layer.key}.png`
      img.onload = () => {
        const off = document.createElement('canvas')
        off.width = img.naturalWidth
        off.height = img.naturalHeight
        const octx = off.getContext('2d')
        if (!octx) return
        octx.drawImage(img, 0, 0)
        grayDataRef.current[layer.key] = octx.getImageData(0, 0, off.width, off.height)
        loadedCountRef.current += 1
        if (loadedCountRef.current === PROCEDURAL_LAYERS.length) {
          recolorAll()
          draw()
        }
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function recolorAll() {
    const lut = buildLookupTable(style)
    PROCEDURAL_LAYERS.forEach((layer) => {
      const gray = grayDataRef.current[layer.key]
      if (!gray) return
      const canvas = document.createElement('canvas')
      canvas.width = gray.width
      canvas.height = gray.height
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const out = ctx.createImageData(gray.width, gray.height)
      for (let i = 0; i < gray.data.length; i += 4) {
        const v = gray.data[i]
        out.data[i] = lut[v * 3]
        out.data[i + 1] = lut[v * 3 + 1]
        out.data[i + 2] = lut[v * 3 + 2]
        out.data[i + 3] = 255
      }
      ctx.putImageData(out, 0, 0)
      colorizedRef.current[layer.key] = canvas
    })
  }

  function draw() {
    const outCanvas = outputCanvasRef.current
    if (!outCanvas) return
    const ctx = outCanvas.getContext('2d')
    if (!ctx) return

    const W = outCanvas.width
    const H = outCanvas.height
    ctx.clearRect(0, 0, W, H)

    const weights = getLayerWeights(halfWidthMpc)

    // Ordre du plus grand (coarse) au plus petit (fin) — cohérent avec la
    // construction emboîtée des textures (§4.4 du document d'architecture).
    for (let i = PROCEDURAL_LAYERS.length - 1; i >= 0; i--) {
      const layer = PROCEDURAL_LAYERS[i]
      const w = weights[layer.key]
      if (w < 0.003) continue
      const source = colorizedRef.current[layer.key]
      if (!source) continue

      const n = source.width
      const frac = Math.min(halfWidthMpc / layer.maxMpc, 1)
      const cropSize = Math.max(Math.round(n * frac), 2)
      const start = Math.round((n - cropSize) / 2)

      ctx.globalAlpha = w
      ctx.drawImage(source, start, start, cropSize, cropSize, 0, 0, W, H)
    }
    ctx.globalAlpha = 1
  }

  // Recoloration complète quand le style change.
  useEffect(() => {
    if (loadedCountRef.current === PROCEDURAL_LAYERS.length) {
      recolorAll()
      draw()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style])

  // Redessin (recadrage/fondu) quand le zoom change.
  useEffect(() => {
    if (loadedCountRef.current === PROCEDURAL_LAYERS.length) {
      draw()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [halfWidthMpc])

  return (
    <canvas
      ref={outputCanvasRef}
      width={512}
      height={512}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        opacity,
        borderRadius: 8,
      }}
    />
  )
}
