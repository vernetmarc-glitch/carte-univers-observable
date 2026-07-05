import { useEffect, useRef } from 'react'
import { buildLookupTable, type DensityStyle } from './colormaps'
import { getLayerWeights } from './layerWeights'

interface ProceduralLayer {
  key: 'l2' | 'l3' | 'l4' | 'l4b' | 'l5'
  maxMpc: number
}

// Du plus petit au plus grand — cf. document d'architecture §4.1. Le layer 1
// (local) est géré séparément par MilkyWayLayer (rendu de points, pas une
// texture), et n'apparaît donc pas ici.
const PROCEDURAL_LAYERS: ProceduralLayer[] = [
  { key: 'l2', maxMpc: 30 },
  { key: 'l3', maxMpc: 150 },
  { key: 'l4', maxMpc: 300 },
  { key: 'l4b', maxMpc: 2100 },
  { key: 'l5', maxMpc: 14570 },
]

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
