import { useEffect, useMemo, useRef, useState } from 'react'
import { densityDilutionFactor, type CosmologyState } from './cosmology'
import DensityLayer from './DensityLayer'
import MilkyWayLayer from './MilkyWayLayer'
import LocalGroupLayer from './LocalGroupLayer'
import { DENSITY_STYLE_LABELS, type DensityStyle } from './colormaps'

/**
 * Phase 2 (grille comobile + zoom) + Phase 3 (temps + effets d'expansion).
 *
 * Disposition demandée : le zoom est un curseur VERTICAL sur le bord de la
 * carte ; le temps est un curseur HORIZONTAL sous la carte (à l'emplacement
 * qu'occupait le zoom auparavant).
 */

const MIN_HALF_WIDTH_MPC = 0.02 // ~65 000 al — la Voie lactée (rayon 52 000 al) remplit le cadre
const MAX_HALF_WIDTH_MPC = 14570 // ~95 Gal de côté au total
const GLY_PER_MPC = 3.26156e-3

interface LayerDef {
  name: string
  maxMpc: number
  color: string
}

const LAYERS: LayerDef[] = [
  { name: 'Local (Voie lactée, Groupe Local)', maxMpc: 3, color: '#7fd1ff' },
  { name: 'Amas de galaxies', maxMpc: 30, color: '#7fffb0' },
  { name: 'Toile cosmique (filaments, vides)', maxMpc: 150, color: '#ffe37f' },
  { name: "Transition vers l'homogénéité", maxMpc: 300, color: '#ffb37f' },
  { name: 'Univers homogène', maxMpc: MAX_HALF_WIDTH_MPC, color: '#ff7f9d' },
]

function activeLayer(halfWidthMpc: number): LayerDef {
  return LAYERS.find((l) => halfWidthMpc <= l.maxMpc) ?? LAYERS[LAYERS.length - 1]
}

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

interface UniverseMapProps {
  cosmology: CosmologyState
  tGyr: number
  tMin: number
  tMax: number
  onTimeChange: (t: number) => void
}

export default function UniverseMap({ cosmology, tGyr, tMin, tMax, onTimeChange }: UniverseMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [logHalfWidth, setLogHalfWidth] = useState(Math.log10(MAX_HALF_WIDTH_MPC))
  const [densityStyle, setDensityStyle] = useState<DensityStyle>('astro')
  const [densityPresence, setDensityPresence] = useState(1.0)
  const halfWidthMpc = Math.pow(10, logHalfWidth)
  const layer = activeLayer(halfWidthMpc)
  const dilution = densityDilutionFactor(cosmology.a)

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
  const gridStepPhysicalGly = gridStepMpc * cosmology.a * GLY_PER_MPC

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const size = canvas.width
    const pxPerMpc = size / (2 * halfWidthMpc)
    const cx = size / 2
    const cy = size / 2

    // Fond transparent : la couche de densité (DensityLayer) est affichée en dessous.
    // On garde juste une très légère brume, modulée par la dilution, pour le confort visuel.
    ctx.clearRect(0, 0, size, size)
    const densityGlow = Math.min(0.08, 0.012 * Math.log10(dilution + 1))
    ctx.fillStyle = `rgba(10, 10, 20, ${0.15 + densityGlow})`
    ctx.fillRect(0, 0, size, size)

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

    const horizonRPx = cosmology.chiParticleComovingMpc * pxPerMpc
    ctx.strokeStyle = '#5aa9e6'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(cx, cy, horizonRPx, 0, Math.PI * 2)
    ctx.stroke()
    if (horizonRPx < size * 0.9) {
      ctx.fillStyle = '#5aa9e6'
      ctx.font = 'bold 11px monospace'
      ctx.fillText('Horizon des particules', cx + 6, cy - horizonRPx + 14)
    }

    // Le marqueur de position s'estompe aux grandes échelles : montrer un point
    // "nous" bien visible n'a plus de sens à l'échelle de l'univers homogène.
    const markerFadeStart = 300 // Mpc — début de l'estompage (frontière L4/L4b)
    const markerFadeEnd = 14570 // Mpc — quasi invisible à l'échelle max
    const markerT = Math.min(
      Math.max(
        (Math.log10(halfWidthMpc) - Math.log10(markerFadeStart)) /
          (Math.log10(markerFadeEnd) - Math.log10(markerFadeStart)),
        0
      ),
      1
    )
    const markerAlpha = 1 - markerT * 0.92 // ne descend jamais à 0 complet, juste très discret

    ctx.fillStyle = `rgba(255,255,255,${markerAlpha})`
    ctx.beginPath()
    ctx.arc(cx, cy, 3, 0, Math.PI * 2)
    ctx.fill()
  }, [halfWidthMpc, gridStepMpc, cosmology, dilution])

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: '#999' }}>Style :</span>
          {(Object.keys(DENSITY_STYLE_LABELS) as DensityStyle[]).map((s) => (
            <button
              key={s}
              onClick={() => setDensityStyle(s)}
              style={{
                background: densityStyle === s ? '#2a2a3a' : 'transparent',
                color: densityStyle === s ? '#fff' : '#999',
                border: '1px solid #333',
                borderRadius: 6,
                padding: '3px 10px',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              {DENSITY_STYLE_LABELS[s]}
            </button>
          ))}
          <span style={{ fontSize: 11, color: '#999', marginLeft: 12 }}>Présence du fond :</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.02}
            value={densityPresence}
            onChange={(e) => setDensityPresence(Number(e.target.value))}
            style={{ width: 100 }}
          />
        </div>

        <div style={{ position: 'relative', width: '100%', maxWidth: 640, aspectRatio: '1/1' }}>
          <DensityLayer style={densityStyle} opacity={densityPresence} halfWidthMpc={halfWidthMpc} />
          <LocalGroupLayer halfWidthMpc={halfWidthMpc} opacity={densityPresence} style={densityStyle} />
          <MilkyWayLayer halfWidthMpc={halfWidthMpc} opacity={densityPresence} style={densityStyle} />
          <canvas
            ref={canvasRef}
            width={640}
            height={640}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              borderRadius: 8,
              touchAction: 'none',
              display: 'block',
            }}
          />
          <div
            style={{
              position: 'absolute',
              bottom: 8,
              left: 10,
              maxWidth: 'calc(100% - 20px)',
              width: 230,
              fontSize: 11,
              color: layer.color,
              background: 'rgba(0,0,0,0.45)',
              padding: '2px 8px',
              borderRadius: 4,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              boxSizing: 'border-box',
            }}
          >
            {layer.name}
          </div>
        </div>

        <div style={{ marginTop: 12, maxWidth: 640 }}>
          <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
            Temps — âge de l'univers : <strong>{tGyr.toLocaleString('fr-FR', { maximumFractionDigits: 4 })} Ga</strong>{' '}
            (z = {cosmology.z.toLocaleString('fr-FR', { maximumFractionDigits: 3 })})
          </label>
          <input
            type="range"
            min={tMin}
            max={tMax}
            step={(tMax - tMin) / 3000}
            value={tGyr}
            onChange={(e) => onTimeChange(Number(e.target.value))}
            style={{ width: '100%' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#777' }}>
            <span>Recombinaison</span>
            <span>Aujourd'hui</span>
          </div>
          <p style={{ fontSize: 11, color: '#666' }}>
            1 case de grille ({formatDistance(gridStepMpc)} comobiles) représentait alors une distance physique
            réelle de <strong>{gridStepPhysicalGly < 0.001 ? (gridStepPhysicalGly * 1e6).toFixed(0) + ' al' : gridStepPhysicalGly.toFixed(4) + ' Gal'}</strong>{' '}
            — dilution de densité ×{dilution.toLocaleString('fr-FR', { maximumFractionDigits: dilution > 100 ? 0 : 1 })} par rapport à aujourd'hui.
          </p>
          <p style={{ fontSize: 10, color: '#555' }}>
            Voie lactée + Groupe Local (galaxies voisines réelles, positions angulaires simplifiées) +
            4 layers procéduraux avec héritage hiérarchique. Le temps n'affecte pas encore visuellement
            la densité — prochaine étape.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 48 }}>
        <span style={{ fontSize: 10, color: '#999', writingMode: 'vertical-rl', marginBottom: 4 }}>zoom +</span>
        <div style={{ width: 40, height: 460, position: 'relative', touchAction: 'none' }}>
          <input
            type="range"
            min={Math.log10(MIN_HALF_WIDTH_MPC)}
            max={Math.log10(MAX_HALF_WIDTH_MPC)}
            step={0.002}
            value={logHalfWidth}
            onChange={(e) => setLogHalfWidth(Number(e.target.value))}
            style={{
              position: 'absolute',
              width: 460,
              height: 32,
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%) rotate(90deg)',
              margin: 0,
              touchAction: 'none',
            }}
          />
        </div>
        <span style={{ fontSize: 10, color: '#999', writingMode: 'vertical-rl', marginTop: 4 }}>zoom −</span>
      </div>
    </div>
  )
}
