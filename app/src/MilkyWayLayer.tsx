import { useEffect, useRef, useState } from 'react'
import { getLayerWeights } from './layerWeights'
import { colorForValue, type DensityStyle } from './colormaps'

// Le module GalaxyModel est chargé globalement via <script> dans index.html
// (CDN jsDelivr, source de vérité unique partagée avec "Le silence du cosmos").
interface GalaxyStar {
  gx: number
  gy: number
  b: number
  sz: number
}
interface GalaxyModelApi {
  MW_R: number
  YSCALE: number
  generateGalaxy: (opts?: { seed?: number; starCount?: number }) => GalaxyStar[]
  galacticToScreen: (
    gx: number,
    gy: number,
    scale: number,
    originX: number,
    originY: number
  ) => { x: number; y: number }
  starColor: (b: number) => string
}
declare global {
  interface Window {
    GalaxyModel?: GalaxyModelApi
  }
}

const LY_PER_MPC = 3.26156e6

interface MilkyWayLayerProps {
  halfWidthMpc: number
  opacity: number
  style: DensityStyle
}

export default function MilkyWayLayer({ halfWidthMpc, opacity, style }: MilkyWayLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const starsRef = useRef<GalaxyStar[] | null>(null)
  const rafRef = useRef<number | null>(null)
  const [ready, setReady] = useState(false)

  // Génération unique des étoiles (seed fixe -> toujours les mêmes, cf. gouvernance du modèle partagé).
  useEffect(() => {
    let cancelled = false
    function tryInit() {
      if (window.GalaxyModel) {
        starsRef.current = window.GalaxyModel.generateGalaxy()
        if (!cancelled) setReady(true)
      } else {
        setTimeout(tryInit, 100)
      }
    }
    tryInit()
    return () => {
      cancelled = true
    }
  }, [])

  const weight = getLayerWeights(halfWidthMpc).milkyway

  // Redessin throttlé via requestAnimationFrame : pendant un glissement rapide du
  // curseur de zoom, de nombreux changements d'état arrivent plus vite que le
  // taux de rafraîchissement — on n'exécute alors qu'un seul rendu par frame
  // (le plus récent), au lieu de bloquer le thread principal à chaque événement.
  useEffect(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)

    rafRef.current = requestAnimationFrame(() => {
      const canvas = canvasRef.current
      const stars = starsRef.current
      const gm = window.GalaxyModel
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const size = canvas.width
      if (!stars || !gm || weight < 0.003) {
        ctx.clearRect(0, 0, size, size)
        return
      }

      const halfWidthLy = halfWidthMpc * LY_PER_MPC
      const scale = size / 2 / halfWidthLy
      const originX = size / 2
      const originY = size / 2
      const margin = 8

      ctx.clearRect(0, 0, size, size)
      ctx.fillStyle = 'rgb(0,0,4)'
      ctx.fillRect(0, 0, size, size)

      for (let i = 0; i < stars.length; i++) {
        const star = stars[i]
        const x = originX + star.gx * scale
        const y = originY + star.gy * scale * gm.YSCALE // aplatissement (constante partagée, non redéfinie)
        if (x < -margin || x > size + margin || y < -margin || y > size + margin) continue
        const r = Math.max(star.sz * scale * 400, 0.4)
        const [cr, cg, cb] = colorForValue(Math.min(star.b + 0.15, 1), style)
        ctx.fillStyle = `rgb(${cr},${cg},${cb})`
        ctx.globalAlpha = Math.min(star.b + 0.3, 1)
        ctx.beginPath()
        ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    })

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [halfWidthMpc, ready, weight, style])

  return (
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
        opacity: opacity * weight,
        borderRadius: 8,
      }}
    />
  )
}
