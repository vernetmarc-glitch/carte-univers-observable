import { useEffect, useRef, useState } from 'react'
import { getLayerWeights } from './layerWeights'
import { colorForValue, type DensityStyle } from './colormaps'
import { onGalaxyReady, type GalaxyStar, type GalaxyModelApi } from './galaxyModelLoader'
import { generateNearbyGalaxyStars } from './nearbyGalaxyStars'

const LY_PER_MPC = 3.26156e6

interface CatalogGalaxy {
  name: string | null
  distanceMpc: number
  radiusMpc: number
  angleDeg: number
  brightness: number
  isReal: boolean
}

interface LocalGroupLayerProps {
  halfWidthMpc: number
  opacity: number
  style: DensityStyle
  width: number
  height: number
  dpr: number
}

export default function LocalGroupLayer({ halfWidthMpc, opacity, style, width, height, dpr }: LocalGroupLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number | null>(null)
  const starsRef = useRef<GalaxyStar[] | null>(null)
  const gmRef = useRef<GalaxyModelApi | null>(null)
  const catalogRef = useRef<CatalogGalaxy[] | null>(null)
  const [starsReady, setStarsReady] = useState(false)
  const [catalogReady, setCatalogReady] = useState(false)

  useEffect(() => {
    return onGalaxyReady((stars, gm) => {
      starsRef.current = stars
      gmRef.current = gm
      setStarsReady(true)
    })
  }, [])

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/local_group_catalog.json`)
      .then((res) => res.json())
      .then((catalog: CatalogGalaxy[]) => {
        catalogRef.current = catalog.filter((g) => g.isReal)
        setCatalogReady(true)
      })
  }, [])

  const weight = getLayerWeights(halfWidthMpc).localgroup

  useEffect(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)

    rafRef.current = requestAnimationFrame(() => {
      const canvas = canvasRef.current
      if (!canvas || width < 1 || height < 1) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const W = canvas.width
      const H = canvas.height
      ctx.clearRect(0, 0, W, H)
      if (weight < 0.003) return

      const shortSide = Math.min(W, H)
      const scale = shortSide / 2 / halfWidthMpc // px par Mpc
      const originX = W / 2
      const originY = H / 2

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
          if (x < -2 * dpr || x > W + 2 * dpr || y < -2 * dpr || y > H + 2 * dpr) continue
          const r = Math.max(star.sz * scalePerLy * 400, 0.3 * dpr)
          const [cr, cg, cb] = colorForValue(Math.min(star.b + 0.15, 1), style)
          ctx.fillStyle = `rgb(${cr},${cg},${cb})`
          ctx.globalAlpha = Math.min(star.b + 0.3, 1)
          ctx.beginPath()
          ctx.arc(x, y, r, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalAlpha = 1
      }

      // --- Galaxies réelles voisines : semis de points (pas une tache),
      // dimensionné sur leur vrai rayon (radiusMpc), positionné à leur vraie
      // distance/angle — cohérent visuellement avec la Voie lactée.
      const catalog = catalogRef.current
      if (catalog) {
        for (const gal of catalog) {
          const rad = (gal.angleDeg * Math.PI) / 180
          const centerX = originX + Math.cos(rad) * gal.distanceMpc * scale
          const centerY = originY + Math.sin(rad) * gal.distanceMpc * scale
          const galRadiusPx = gal.radiusMpc * scale
          if (
            centerX < -galRadiusPx - 4 ||
            centerX > W + galRadiusPx + 4 ||
            centerY < -galRadiusPx - 4 ||
            centerY > H + galRadiusPx + 4
          )
            continue

          const seed = (gal.name?.length ?? 1) * 7919 + Math.round(gal.distanceMpc * 100000)
          const galStars = generateNearbyGalaxyStars(gal.name ?? '', gal.radiusMpc, gal.brightness, seed)
          for (const s of galStars) {
            const x = centerX + s.dx * scale
            const y = centerY + s.dy * scale
            const r = Math.max(0.35 * dpr, galRadiusPx * 0.02)
            const [cr, cg, cb] = colorForValue(Math.min(s.b + gal.brightness * 0.2, 1), style)
            ctx.fillStyle = `rgb(${cr},${cg},${cb})`
            ctx.globalAlpha = Math.min(s.b + 0.25, 1)
            ctx.beginPath()
            ctx.arc(x, y, r, 0, Math.PI * 2)
            ctx.fill()
          }
        }
        ctx.globalAlpha = 1
      }
    })

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [halfWidthMpc, weight, style, starsReady, catalogReady, width, height, dpr])

  return (
    <canvas
      ref={canvasRef}
      width={Math.max(Math.round(width), 1)}
      height={Math.max(Math.round(height), 1)}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        opacity: opacity * weight,
      }}
    />
  )
}
