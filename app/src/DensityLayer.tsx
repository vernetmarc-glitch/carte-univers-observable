import { useEffect, useRef } from 'react'
import { type DensityStyle } from './colormaps'
import { getLayerWeights } from './layerWeights'
import { processDensityField } from './densityStyle'

const STYLE_WORKING_RES = 256 // résolution utilisée lors de la calibration (glow-test.html)

// Marge de génération des textures (cf. scripts/generate_layers.py et
// generate_local_group_texture.py) : chaque texture couvre en réalité
// layer.maxMpc * MARGIN_FACTOR de demi-largeur physique, pas seulement
// layer.maxMpc — nécessaire pour le futur recadrage rectangulaire (portrait/
// paysage) sans letterboxing. Garder cette valeur synchronisée avec le Python.
const MARGIN_FACTOR = 1.5

interface ProceduralLayer {
  key: 'localgroup' | 'l2' | 'l3' | 'l4' | 'l4b' | 'l5'
  maxMpc: number
}

// Du plus petit au plus grand — cf. document d'architecture §4.1. "localgroup"
// est maintenant une texture statique (comme les autres), générée hors-ligne
// par scripts/generate_local_group_texture.py — plus de calcul par frame.
const PROCEDURAL_LAYERS: ProceduralLayer[] = [
  { key: 'localgroup', maxMpc: 2.4 },
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
    PROCEDURAL_LAYERS.forEach((layer) => {
      const gray = grayDataRef.current[layer.key]
      if (!gray) return

      // Sous-échantillonnage à la résolution de calibration (256) avant le
      // pipeline de style (netteté, points...), pour un rendu fidèle à
      // glow-test.html plutôt qu'à la résolution native de la texture (512).
      const down = document.createElement('canvas')
      down.width = STYLE_WORKING_RES
      down.height = STYLE_WORKING_RES
      const dctx = down.getContext('2d')
      if (!dctx) return
      const src = document.createElement('canvas')
      src.width = gray.width
      src.height = gray.height
      src.getContext('2d')!.putImageData(gray, 0, 0)
      dctx.drawImage(src, 0, 0, STYLE_WORKING_RES, STYLE_WORKING_RES)
      const downGray = dctx.getImageData(0, 0, STYLE_WORKING_RES, STYLE_WORKING_RES)

      const grayValues = new Float32Array(STYLE_WORKING_RES * STYLE_WORKING_RES)
      for (let i = 0; i < grayValues.length; i++) grayValues[i] = downGray.data[i * 4] / 255

      const processed = processDensityField(grayValues, STYLE_WORKING_RES, style)

      const canvas = document.createElement('canvas')
      canvas.width = STYLE_WORKING_RES
      canvas.height = STYLE_WORKING_RES
      canvas.getContext('2d')!.putImageData(processed, 0, 0)
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
      const frac = Math.min(halfWidthMpc / (layer.maxMpc * MARGIN_FACTOR), 1)
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
