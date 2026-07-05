import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * Phase 2 — Grille comobile fixe + zoom.
 *
 * La carte représente une grille en coordonnées COMOBILES, qui ne bouge
 * jamais : seul le champ de vue (la portion de grille visible) change avec
 * le zoom. C'est la brique de base sur laquelle viendront se greffer :
 *  - la dilution de densité et le cercle d'horizon animés par le temps (Phase 3)
 *  - les layers de matière (Phase 4)
 *  - les 3 sphères cosmologiques en overlay (Phase 5)
 */

// Bornes du zoom, en demi-largeur de champ de vue, en Mpc comobiles.
// - MIN : échelle locale (Groupe Local, layer 1 du document d'architecture)
// - MAX : la carte complète (~95 Gal de large, layer 5)
const MIN_HALF_WIDTH_MPC = 1
const MAX_HALF_WIDTH_MPC = 14570 // ~95 Gal de côté au total

const GLY_PER_MPC = 3.26156e-3

interface LayerDef {
  name: string
  minMpc: number
  maxMpc: number
  color: string
}

// Cf. document d'architecture §4.1 — bornes en échelle comobile.
const LAYERS: LayerDef[] = [
  { name: 'Local (Voie lactée, Groupe Local)', minMpc: 0, maxMpc: 3, color: '#7fd1ff' },
  { name: 'Amas de galaxies', minMpc: 3, maxMpc: 30, color: '#7fffb0' },
  { name: 'Toile cosmique (filaments, vides)', minMpc: 30, maxMpc: 150, color: '#ffe37f' },
  { name: "Transition vers l'homogénéité", minMpc: 150, maxMpc: 300, color: '#ffb37f' },
  { name: 'Univers homogène', minMpc: 300, maxMpc: MAX_HALF_WIDTH_MPC, color: '#ff7f9d' },
]

function activeLayer(halfWidthMpc: number): LayerDef {
  return LAYERS.find((l) => halfWidthMpc <= l.maxMpc) ?? LAYERS[LAYERS.length - 1]
}

function formatDistance(mpc: number): string {
  const gly = mpc * GLY_PER_MPC
  if (gly >= 1) return `${gly.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} Gal`
  const mly = gly * 1000
  if (mly >= 1) return `${mly.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mal`
  return `${mpc.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} Mpc`
}

/** Choisit un pas de grille "rond" (1-2-5 × 10^n) proche de target. */
function niceGridStep(target: number): number {
  const exp = Math.floor(Math.log10(target))
  const base = target / Math.pow(10, exp)
  const niceBase = base < 1.5 ? 1 : base < 3.5 ? 2 : base < 7.5 ? 5 : 10
  return niceBase * Math.pow(10, exp)
}

export default function UniverseMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Zoom stocké en log10(demi-largeur en Mpc) pour un curseur perceptuellement linéaire.
  const [logHalfWidth, setLogHalfWidth] = useState(Math.log10(MAX_HALF_WIDTH_MPC))
  const halfWidthMpc = Math.pow(10, logHalfWidth)
  const layer = activeLayer(halfWidthMpc)

  // Zoom à la molette / pincement, en plus du curseur.
  useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setLogHalfWidth((v) => {
        const next = v + e.deltaY * 0.001
        return Math.min(Math.max(next, Math.log10(MIN_HALF_WIDTH_MPC)), Math.log10(MAX_HALF_WIDTH_MPC))
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  const gridStepMpc = useMemo(() => niceGridStep(halfWidthMpc / 4), [halfWidthMpc])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const size = canvas.width // canvas carré
    const pxPerMpc = size / (2 * halfWidthMpc)
    const cx = size / 2
    const cy = size / 2

    ctx.fillStyle = '#05050a'
    ctx.fillRect(0, 0, size, size)

    // --- Grille carrée (lignes comobiles fixes) ---
    ctx.strokeStyle = 'rgba(255,255,255,0.12)'
    ctx.lineWidth = 1
    const nLines = Math.ceil(halfWidthMpc / gridStepMpc) + 1
    for (let i = -nLines; i <= nLines; i++) {
      const posMpc = i * gridStepMpc
      const px = cx + posMpc * pxPerMpc
      if (px >= 0 && px <= size) {
        ctx.beginPath()
        ctx.moveTo(px, 0)
        ctx.lineTo(px, size)
        ctx.stroke()
      }
      const py = cy + posMpc * pxPerMpc
      if (py >= 0 && py <= size) {
        ctx.beginPath()
        ctx.moveTo(0, py)
        ctx.lineTo(size, py)
        ctx.stroke()
      }
    }

    // --- Anneaux de distance (repères radiaux) ---
    ctx.strokeStyle = 'rgba(255,255,255,0.22)'
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    ctx.font = '11px monospace'
    for (let i = 1; i <= nLines; i++) {
      const rMpc = i * gridStepMpc
      const rPx = rMpc * pxPerMpc
      if (rPx > size * 0.75) break
      ctx.beginPath()
      ctx.arc(cx, cy, rPx, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fillText(formatDistance(rMpc), cx + 4, cy - rPx - 4)
    }

    // --- Position de l'observateur (nous) ---
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(cx, cy, 3, 0, Math.PI * 2)
    ctx.fill()
  }, [halfWidthMpc, gridStepMpc])

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={640}
        height={640}
        style={{ width: '100%', maxWidth: 640, aspectRatio: '1/1', borderRadius: 8, touchAction: 'none' }}
      />
      <div style={{ marginTop: 12 }}>
        <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
          Zoom — demi-champ de vue : <strong>{formatDistance(halfWidthMpc)}</strong>{' '}
          <span style={{ color: layer.color }}>● {layer.name}</span>
        </label>
        <input
          type="range"
          min={Math.log10(MIN_HALF_WIDTH_MPC)}
          max={Math.log10(MAX_HALF_WIDTH_MPC)}
          step={0.002}
          value={logHalfWidth}
          onChange={(e) => setLogHalfWidth(Number(e.target.value))}
          style={{ width: '100%', maxWidth: 640 }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', maxWidth: 640, fontSize: 11, color: '#777' }}>
          <span>Local (~{formatDistance(MIN_HALF_WIDTH_MPC)})</span>
          <span>Univers observable (~{formatDistance(MAX_HALF_WIDTH_MPC)})</span>
        </div>
        <p style={{ fontSize: 11, color: '#666', maxWidth: 640 }}>
          Molette / pincement pour zoomer directement sur la carte. La grille est fixe en coordonnées
          comobiles — c'est le champ de vue qui change, pas la grille elle-même (cf. §2 du document
          d'architecture). Le pas de grille affiché : {formatDistance(gridStepMpc)}.
        </p>
      </div>
    </div>
  )
}
