import { useEffect, useRef, useState } from 'react'
import { getLayerWeights } from './layerWeights'
import { colorForValue, type DensityStyle } from './colormaps'
import { onGalaxyReady, type GalaxyStar, type GalaxyModelApi } from './galaxyModelLoader'

const LY_PER_MPC = 3.26156e6

interface LocalGroupLayerProps {
  halfWidthMpc: number
  opacity: number
  style: DensityStyle
}

export default function LocalGroupLayer({ halfWidthMpc, opacity, style }: LocalGroupLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number | null>(null)
  const starsRef = useRef<GalaxyStar[] | null>(null)
  const gmRef = useRef<GalaxyModelApi | null>(null)
  const [starsReady, setStarsReady] = useState(false)

  useEffect(() => {
    return onGalaxyReady((stars, gm) => {
      starsRef.current = stars
      gmRef.current = gm
      setStarsReady(true)
    })
  }, [])

  const weight = getLayerWeights(halfWidthMpc).localgroup

  useEffect(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)

    rafRef.current = requestAnimationFrame(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const size = canvas.width
      ctx.clearRect(0, 0, size, size)
      if (weight < 0.003) return

      const scale = size / 2 / halfWidthMpc // px par Mpc
      const originX = size / 2
      const originY = size / 2

      // --- Notre propre galaxie : même forme que sur le layer "Voie lactée",
      // juste rendue à l'échelle du Mpc au lieu de l'année-lumière. Utilise le
      // même cache d'étoiles -> aucune discontinuité de forme à la transition.
      const stars = starsRef.current
      const gm = gmRef.current
      if (stars && gm) {
        const scalePerLy = scale / LY_PER_MPC
        for (let i = 0; i < stars.length; i++) {
          const star = stars[i]
          const x = originX + star.gx * scalePerLy
          const y = originY + star.gy * scalePerLy * gm.YSCALE
          if (x < -2 || x > size + 2 || y < -2 || y > size + 2) continue
          const r = Math.max(star.sz * scalePerLy * 400, 0.3)
          const [cr, cg, cb] = colorForValue(Math.min(star.b + 0.15, 1), style)
          ctx.fillStyle = `rgb(${cr},${cg},${cb})`
          ctx.globalAlpha = Math.min(star.b + 0.3, 1)
          ctx.beginPath()
          ctx.arc(x, y, r, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalAlpha = 1
      }

      // --- Étiquettes des galaxies désactivées temporairement (perf) : elles
      // n'apportaient pas beaucoup et contribuaient au saccadé pendant le
      // zoom. Le halo/point de chaque galaxie reste affiché via la texture
      // statique (cf. DensityLayer + scripts/generate_local_group_texture.py). ---
    })

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [halfWidthMpc, weight, style, starsReady])

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
