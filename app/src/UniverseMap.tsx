import { useEffect, useMemo, useRef, useState } from 'react'
import { densityDilutionFactor, type CosmologyState } from './cosmology'
import DensityLayer from './DensityLayer'
import MilkyWayLayer from './MilkyWayLayer'
import LocalGroupLayer from './LocalGroupLayer'
import { DENSITY_STYLE_LABELS, type DensityStyle } from './colormaps'

const MIN_HALF_WIDTH_MPC = 0.02 // ~65 000 al — la Voie lactée (rayon 52 000 al) remplit le cadre
const MAX_HALF_WIDTH_MPC = 14570 // ~95 Gal de côté au total
const GLY_PER_MPC = 3.26156e-3

function formatDistance(mpc: number): string {
  const gly = mpc * GLY_PER_MPC
  if (gly >= 1) return `${gly.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} Gal`
  const mly = gly * 1000
  if (mly >= 1) return `${mly.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mal`
  const ly = mly * 1e6
  return `${Math.round(ly).toLocaleString('fr-FR')} al`
}

function niceGridStep(target: number): number {
  const exp = Math.floor(Math.log10(target))
  const base = target / Math.pow(10, exp)
  const niceBase = base < 1.5 ? 1 : base < 3.5 ? 2 : base < 7.5 ? 5 : 10
  return niceBase * Math.pow(10, exp)
}

/** Suit la taille réelle (en pixels) d'un conteneur, pour un rendu plein écran non déformé. */
function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return [ref, size] as const
}

interface UniverseMapProps {
  cosmology: CosmologyState
  tGyr: number
  tMin: number
  tMax: number
  onTimeChange: (t: number) => void
}

export default function UniverseMap({ cosmology, tGyr, tMin, tMax, onTimeChange }: UniverseMapProps) {
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>()
  const [zoomSliderRef, zoomSliderSize] = useElementSize<HTMLDivElement>()
  const gridCanvasRef = useRef<HTMLCanvasElement>(null)
  const [logHalfWidth, setLogHalfWidth] = useState(Math.log10(MAX_HALF_WIDTH_MPC))
  const [densityStyle, setDensityStyle] = useState<DensityStyle>('astro')
  const [densityPresence, setDensityPresence] = useState(1.0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const halfWidthMpc = Math.pow(10, logHalfWidth)
  const dilution = densityDilutionFactor(cosmology.a)

  // Zoom à la molette, sur toute la zone de carte.
  useEffect(() => {
    const el = containerRef.current
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const gridStepMpc = useMemo(() => niceGridStep(halfWidthMpc / 4), [halfWidthMpc])

  useEffect(() => {
    const canvas = gridCanvasRef.current
    if (!canvas || width < 1 || height < 1) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width
    const H = canvas.height
    const shortSide = Math.min(W, H)
    const pxPerMpc = shortSide / (2 * halfWidthMpc)
    const cx = W / 2
    const cy = H / 2

    // Fond transparent : la couche de densité (DensityLayer) est affichée en dessous.
    ctx.clearRect(0, 0, W, H)
    const densityGlow = Math.min(0.08, 0.012 * Math.log10(dilution + 1))
    ctx.fillStyle = `rgba(10, 10, 20, ${0.15 + densityGlow})`
    ctx.fillRect(0, 0, W, H)

    ctx.strokeStyle = 'rgba(255,255,255,0.12)'
    ctx.lineWidth = 1
    const nLinesX = Math.ceil(W / 2 / pxPerMpc / gridStepMpc) + 1
    const nLinesY = Math.ceil(H / 2 / pxPerMpc / gridStepMpc) + 1
    for (let i = -nLinesX; i <= nLinesX; i++) {
      const px = cx + i * gridStepMpc * pxPerMpc
      if (px >= 0 && px <= W) {
        ctx.beginPath()
        ctx.moveTo(px, 0)
        ctx.lineTo(px, H)
        ctx.stroke()
      }
    }
    for (let i = -nLinesY; i <= nLinesY; i++) {
      const py = cy + i * gridStepMpc * pxPerMpc
      if (py >= 0 && py <= H) {
        ctx.beginPath()
        ctx.moveTo(0, py)
        ctx.lineTo(W, py)
        ctx.stroke()
      }
    }

    ctx.strokeStyle = 'rgba(255,255,255,0.22)'
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    ctx.font = '11px monospace'
    const maxRingLines = Math.max(nLinesX, nLinesY)
    const maxRingPx = Math.max(W, H) * 0.75
    for (let i = 1; i <= maxRingLines; i++) {
      const rMpc = i * gridStepMpc
      const rPx = rMpc * pxPerMpc
      if (rPx > maxRingPx) break
      ctx.beginPath()
      ctx.arc(cx, cy, rPx, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fillText(formatDistance(rMpc), cx + 4, cy - rPx - 4)
    }

    const horizonRPx = cosmology.chiParticleComovingMpc * pxPerMpc
    ctx.strokeStyle = '#5aa9e6'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(cx, cy, horizonRPx, 0, Math.PI * 2)
    ctx.stroke()
    if (horizonRPx < Math.max(W, H) * 0.9) {
      ctx.fillStyle = '#5aa9e6'
      ctx.font = 'bold 11px monospace'
      ctx.fillText('Horizon des particules', cx + 6, cy - horizonRPx + 14)
    }

    // Le marqueur de position s'estompe aux grandes échelles.
    const markerFadeStart = 300
    const markerFadeEnd = 14570
    const markerT = Math.min(
      Math.max(
        (Math.log10(halfWidthMpc) - Math.log10(markerFadeStart)) /
          (Math.log10(markerFadeEnd) - Math.log10(markerFadeStart)),
        0
      ),
      1
    )
    const markerAlpha = 1 - markerT * 0.92

    ctx.fillStyle = `rgba(255,255,255,${markerAlpha})`
    ctx.beginPath()
    ctx.arc(cx, cy, 3, 0, Math.PI * 2)
    ctx.fill()
  }, [halfWidthMpc, gridStepMpc, cosmology, dilution, width, height])

  return (
    <div
      ref={containerRef}
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'hidden',
        background: '#05050a',
        touchAction: 'none',
      }}
    >
      {width > 0 && height > 0 && (
        <>
          <DensityLayer style={densityStyle} opacity={densityPresence} halfWidthMpc={halfWidthMpc} width={width} height={height} />
          <LocalGroupLayer halfWidthMpc={halfWidthMpc} opacity={densityPresence} style={densityStyle} width={width} height={height} />
          <MilkyWayLayer halfWidthMpc={halfWidthMpc} opacity={densityPresence} style={densityStyle} width={width} height={height} />
          <canvas
            ref={gridCanvasRef}
            width={Math.round(width)}
            height={Math.round(height)}
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
          />
        </>
      )}

      {/* Titre */}
      <div
        style={{
          position: 'absolute',
          top: 'max(14px, env(safe-area-inset-top))',
          left: 'max(14px, env(safe-area-inset-left))',
          fontSize: 15,
          fontWeight: 600,
          color: '#eee',
          textShadow: '0 1px 4px rgba(0,0,0,0.8)',
          pointerEvents: 'none',
        }}
      >
        Univers observable
      </div>

      {/* Bouton réglages */}
      <button
        onClick={() => setSettingsOpen((v) => !v)}
        style={{
          position: 'absolute',
          top: 'max(10px, env(safe-area-inset-top))',
          right: 'max(10px, env(safe-area-inset-right))',
          width: 32,
          height: 32,
          borderRadius: 16,
          background: 'rgba(20,20,30,0.6)',
          border: '1px solid rgba(255,255,255,0.15)',
          color: '#ccc',
          fontSize: 15,
          cursor: 'pointer',
        }}
        aria-label="Réglages"
      >
        ⚙
      </button>

      {settingsOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(max(10px, env(safe-area-inset-top)) + 40px)',
            right: 'max(10px, env(safe-area-inset-right))',
            background: 'rgba(15,15,22,0.9)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 8,
            padding: 10,
            fontSize: 11,
            color: '#ccc',
            width: 190,
          }}
        >
          <div style={{ marginBottom: 8 }}>Style :</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
            {(Object.keys(DENSITY_STYLE_LABELS) as DensityStyle[]).map((s) => (
              <button
                key={s}
                onClick={() => setDensityStyle(s)}
                style={{
                  background: densityStyle === s ? '#2a2a3a' : 'transparent',
                  color: densityStyle === s ? '#fff' : '#999',
                  border: '1px solid #333',
                  borderRadius: 6,
                  padding: '3px 8px',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                {DENSITY_STYLE_LABELS[s]}
              </button>
            ))}
          </div>
          <div style={{ marginBottom: 4 }}>Présence du fond :</div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.02}
            value={densityPresence}
            onChange={(e) => setDensityPresence(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* Curseur de zoom, vertical, sur le bord droit — s'étire sur toute la hauteur disponible */}
      <div
        ref={zoomSliderRef}
        style={{
          position: 'absolute',
          top: 'calc(max(14px, env(safe-area-inset-top)) + 50px)',
          bottom: 'calc(max(14px, env(safe-area-inset-bottom)) + 56px)',
          right: 'max(6px, env(safe-area-inset-right))',
          width: 40,
          touchAction: 'none',
        }}
      >
        {zoomSliderSize.height > 0 && (
          <input
            type="range"
            min={Math.log10(MIN_HALF_WIDTH_MPC)}
            max={Math.log10(MAX_HALF_WIDTH_MPC)}
            step={0.002}
            value={logHalfWidth}
            onChange={(e) => setLogHalfWidth(Number(e.target.value))}
            style={{
              position: 'absolute',
              // L'input est horizontal puis pivoté de 90° : sa largeur AVANT
              // rotation doit correspondre à la hauteur RÉELLE du conteneur
              // (mesurée via ResizeObserver), pas à sa largeur (40px) — d'où
              // la mesure dynamique plutôt qu'un simple "100%".
              width: zoomSliderSize.height,
              height: 32,
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%) rotate(90deg)',
              transformOrigin: 'center',
              margin: 0,
              touchAction: 'none',
            }}
          />
        )}
      </div>

      {/* Curseur de temps, horizontal, en bas (au-dessus des zones de geste système) */}
      <div
        style={{
          position: 'absolute',
          left: 16,
          right: 56,
          bottom: 'calc(max(14px, env(safe-area-inset-bottom)) + 6px)',
          touchAction: 'none',
        }}
      >
        <input
          type="range"
          min={tMin}
          max={tMax}
          step={(tMax - tMin) / 3000}
          value={tGyr}
          onChange={(e) => onTimeChange(Number(e.target.value))}
          style={{ width: '100%', touchAction: 'none' }}
        />
      </div>
    </div>
  )
}
