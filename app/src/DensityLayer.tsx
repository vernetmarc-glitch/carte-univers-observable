import { useEffect, useRef } from 'react'
import { type DensityStyle } from './colormaps'
import { getLayerWeights } from './layerWeights'
import { processDensityField, getStyleParamsForLayer } from './densityStyle'

// Marge de génération des textures (cf. scripts/generate_layers.py et
// generate_local_group_texture.py) : chaque texture couvre en réalité
// layer.maxMpc * MARGIN_FACTOR de demi-largeur physique, pas seulement
// layer.maxMpc — nécessaire pour le recadrage rectangulaire (portrait/
// paysage) sans letterboxing. Garder cette valeur synchronisée avec le Python.
const MARGIN_FACTOR = 1.5
// L5 est le seul layer visible pile à son bord extrême (zoom maximal absolu
// de la carte) — marge dédiée plus large pour éviter le letterboxing sur les
// écrans très allongés. Cf. scripts/generate_layers.py : MARGIN_FACTOR_L5.
const MARGIN_FACTOR_L5 = 2.4
function marginFor(key: string): number {
  return key === 'l5' ? MARGIN_FACTOR_L5 : MARGIN_FACTOR
}

interface ProceduralLayer {
  key: 'localgroup' | 'l1b' | 'l2' | 'l2b' | 'l3' | 'l3b' | 'l4' | 'l4a' | 'l4b' | 'l5a' | 'l5'
  maxMpc: number
}

// Du plus petit au plus grand — cf. document d'architecture §4.1. "localgroup"
// est la texture des galaxies PROCÉDURALES (non nommées) du Groupe Local
// (cf. scripts/generate_local_group_texture.py) — les galaxies réelles
// nommées sont rendues séparément en points par LocalGroupLayer. Les paliers
// "b"/"a" sont des paliers TECHNIQUES intermédiaires (doublement du nombre
// de layers pour la résolution apparente moyenne), pas de nouveaux layers
// scientifiques — cf. scripts/generate_layers.py.
const PROCEDURAL_LAYERS: ProceduralLayer[] = [
  { key: 'localgroup', maxMpc: 2.4 },
  { key: 'l1b', maxMpc: 8.49 },
  { key: 'l2', maxMpc: 30 },
  { key: 'l2b', maxMpc: 67.08 },
  { key: 'l3', maxMpc: 150 },
  { key: 'l3b', maxMpc: 212.13 },
  { key: 'l4', maxMpc: 300 },
  { key: 'l4a', maxMpc: 793.73 },
  { key: 'l4b', maxMpc: 2100 },
  { key: 'l5a', maxMpc: 5531.46 },
  { key: 'l5', maxMpc: 14570 },
]

interface DensityLayerProps {
  style: DensityStyle
  opacity: number
  halfWidthMpc: number
  width: number
  height: number
  onLoadProgress?: (loaded: number, total: number) => void
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
 *
 * Chargement PROGRESSIF et PRIORISÉ : le layer correspondant au zoom initial
 * est demandé en premier, et chaque texture est traitée/affichée dès son
 * arrivée (pas d'attente des 11 avant le premier rendu) — évite l'attente
 * initiale très longue observée avant cette version.
 */
export default function DensityLayer({ style, opacity, halfWidthMpc, width, height, onLoadProgress }: DensityLayerProps) {
  const outputCanvasRef = useRef<HTMLCanvasElement>(null)
  const grayDataRef = useRef<Record<string, ImageData>>({})
  const colorizedRef = useRef<Record<string, HTMLCanvasElement>>({})
  const loadedCountRef = useRef(0)

  // Chargement des textures sources, PRIORISÉ sur le layer du zoom initial.
  useEffect(() => {
    const ordered = [...PROCEDURAL_LAYERS].sort(
      (a, b) => Math.abs(Math.log(halfWidthMpc / a.maxMpc)) - Math.abs(Math.log(halfWidthMpc / b.maxMpc))
    )
    ordered.forEach((layer) => {
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
        recolorLayer(layer.key)
        draw()
        loadedCountRef.current += 1
        onLoadProgress?.(loadedCountRef.current, PROCEDURAL_LAYERS.length)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function recolorLayer(key: string) {
    const gray = grayDataRef.current[key]
    if (!gray) return

    // Traitement à la résolution NATIVE de la texture (pas de sous-
    // échantillonnage) : le recadrage se fait ensuite sur ce résultat, donc
    // toute perte de résolution ici se répercute directement sur le piqué
    // final à l'écran, en particulier aux niveaux de zoom qui n'utilisent
    // qu'une petite portion de la texture (agrandissement important).
    const n = gray.width
    const grayValues = new Float32Array(n * n)
    for (let i = 0; i < grayValues.length; i++) grayValues[i] = gray.data[i * 4] / 255

    const processed = processDensityField(grayValues, n, style, getStyleParamsForLayer(key))

    const canvas = document.createElement('canvas')
    canvas.width = n
    canvas.height = n
    canvas.getContext('2d')!.putImageData(processed, 0, 0)
    colorizedRef.current[key] = canvas
  }

  function recolorAll() {
    PROCEDURAL_LAYERS.forEach((layer) => recolorLayer(layer.key))
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
      const texturePxPerMpc = n / (2 * layer.maxMpc * marginFor(layer.key))

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
    recolorAll()
    draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style])

  // Redessin (recadrage/fondu) quand le zoom ou la taille de l'écran changent.
  useEffect(() => {
    draw()
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
