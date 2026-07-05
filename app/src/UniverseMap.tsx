import { useEffect, useMemo, useRef, useState } from 'react'
import { densityDilutionFactor, type CosmologyState } from './cosmology'

/**
 * Phase 2 (grille comobile + zoom) + Phase 3 (temps + effets d'expansion).
 *
 * Disposition demandée : le zoom est un curseur VERTICAL sur le bord de la
 * carte ; le temps est un curseur HORIZONTAL sous la carte (à l'emplacement
 * qu'occupait le zoom auparavant).
 */

const MIN_HALF_WIDTH_MPC = 1
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
  return `${mpc.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} Mpc`
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

    const densityGlow = Math.min(0.10, 0.015 * Math.log10(dilution + 1))
    ctx.fillStyle = `rgb(${5 + densityGlow * 400}, ${5 + densityGlow * 300}, ${10 + densityGlow * 500})`
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

    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(cx, cy, 3, 0, Math.PI * 2)
    ctx.fill()
  }, [halfWidthMpc, gridStepMpc, cosmology, dilution])

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <canvas
          ref={canvasRef}
          width={640}
          height={640}
          style={{ width: '100%', maxWidth: 640, aspectRatio: '1/1', borderRadius: 8, touchAction: 'none', display: 'block' }}
        />

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
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 48 }}>
        <span style={{ fontSize: 10, color: '#999', writingMode: 'vertical-rl', marginBottom: 4 }}>zoom +</span>
        <input
          type="range"
          min={Math.log10(MIN_HALF_WIDTH_MPC)}
          max={Math.log10(MAX_HALF_WIDTH_MPC)}
          step={0.002}
          value={logHalfWidth}
          onChange={(e) => setLogHalfWidth(Number(e.target.value))}
          {...({ orient: 'vertical' } as Record<string, string>)}
          style={{
            WebkitAppearance: 'slider-vertical' as any,
            width: 24,
            height: 460,
            flex: 1,
          }}
        />
        <span style={{ fontSize: 10, color: '#999', writingMode: 'vertical-rl', marginTop: 4 }}>zoom −</span>
        <div style={{ fontSize: 10, color: layer.color, textAlign: 'center', marginTop: 8, writingMode: 'vertical-rl' }}>
          {layer.name}
        </div>
      </div>
    </div>
  )
}
