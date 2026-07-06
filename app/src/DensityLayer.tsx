import { useEffect, useRef } from 'react'
import { type DensityStyle } from './colormaps'
import { getLayerWeights } from './layerWeights'
import { processDensityField } from './densityStyle'

const STYLE_WORKING_RES = 512 // proportionnel à la résolution des textures (1024) et à la marge (1.5x)

// Marge de génération des textures (cf. scripts/generate_layers.py et
// generate_local_group_texture.py) : chaque texture couvre en réalité
// layer.maxMpc * MARGIN_FACTOR de demi-largeur physique, pas seulement
// layer.maxMpc — nécessaire pour le recadrage rectangulaire (portrait/
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
  width: number
  height: number
}

/**
 * Couche de densité multi-layers.
 *
 * Charge les textures procédurales (générées hors-ligne, avec héritage
 * hiérarchique entre échelles), les recolore selon le style choisi, puis les
 * mélange avec un fondu doux autour de chaque frontière d'échelle en
 * fonction du zoom courant. Le recadrage est RECTANGULAIRE (proportionnel à
 * width/height) pour remplir tout l'écran sans déformation, en coordonnées
 * flottantes (pas d'arrondi pixel) pour éviter tout jitter au zoom.
 */
export default function DensityLayer({ style, opacity, halfWidthMpc, width, height }: DensityLayerProps) {
  const outputCanvasRef = useRef<HTMLCanvasElement>(null)
  const grayDataRef = useRef<Record<string, ImageData>>({})
  const colorizedRef = useRef<Record<string, HTMLCanvasElement>>({})
  const loadedCountRef = useRef(0)

  // Chargement unique des textures sources en niveaux de gris.
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
    if (!outCanvas || width < 1 || height < 1) return
    const ctx = outCanvas.getContext('2d')
    if (!ctx) return

    const W = outCanvas.width
    const H = outCanvas.height
    ctx.clearRect(0, 0, W, H)

    const weights = getLayerWeights(halfWidthMpc)
    const shortSide = Math.min(W, H)
    // Demi-largeur physique (Mpc) couverte par chaque axe de l'écran — basée
    // sur le côté le plus court pour que "halfWidthMpc" garde son sens de
    // "zoom" habituel, l'autre axe s'étend proportionnellement.
    const halfWidthMpcX = (W / shortSide) * halfWidthMpc
    const halfWidthMpcY = (H / shortSide) * halfWidthMpc

    // Ordre du plus grand (coarse) au plus petit (fin) — cohérent avec la
    // construction emboîtée des textures (§4.4 du document d'architecture).
    for (let i = PROCEDURAL_LAYERS.length - 1; i >= 0; i--) {
      const layer = PROCEDURAL_LAYERS[i]
      const w = weights[layer.key]
      if (w < 0.003) continue
      const source = colorizedRef.current[layer.key]
      if (!source) continue

      const n = source.width // texture carrée (n x n)
      const texturePxPerMpc = n / (2 * layer.maxMpc * MARGIN_FACTOR)

      // Coordonnées FLOTTANTES (pas d'arrondi) : un arrondi au pixel près,
      // une fois agrandi à l'échelle de l'écran, provoquait un jitter très
      // visible aux niveaux de zoom où le recadrage source est petit.
      let cropW = 2 * halfWidthMpcX * texturePxPerMpc
      let cropH = 2 * halfWidthMpcY * texturePxPerMpc

      // Si le recadrage dépasserait la texture source (au-delà de la marge de
      // génération), on réduit LE RECTANGLE DE DESTINATION à l'écran plutôt
      // que le recadrage lui-même — sinon le facteur de compensation annule
      // exactement l'effet du zoom et l'image se fige (le layer arrête de
      // zoomer) tant que le clamp reste actif. En réduisant la destination,
      // le contenu continue de zoomer normalement sur une zone un peu plus
      // petite que l'écran ; le layer plus grossier (déjà visible en fondu à
      // ce moment) comble naturellement les bords.
      let destX = 0
      let destY = 0
      let destW = W
      let destH = H
      const overshoot = Math.max(cropW / n, cropH / n, 1)
      if (overshoot > 1) {
        cropW /= overshoot
        cropH /= overshoot
        destW = W / overshoot
        destH = H / overshoot
        destX = (W - destW) / 2
        destY = (H - destH) / 2
      }
      const startX = (n - cropW) / 2
      const startY = (n - cropH) / 2

      ctx.globalAlpha = w
      ctx.drawImage(source, startX, startY, cropW, cropH, destX, destY, destW, destH)
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

  // Redessin (recadrage/fondu) quand le zoom ou la taille de l'écran changent.
  useEffect(() => {
    if (loadedCountRef.current === PROCEDURAL_LAYERS.length) {
      draw()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [halfWidthMpc, width, height])

  return (
    <canvas
      ref={outputCanvasRef}
      width={Math.max(Math.round(width), 1)}
      height={Math.max(Math.round(height), 1)}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        opacity,
      }}
    />
  )
}
