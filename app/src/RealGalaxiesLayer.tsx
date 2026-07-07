import { useEffect, useRef, useState } from 'react'
import { colorForValue, type DensityStyle } from './colormaps'
import { getStyleParamsForLayer } from './densityStyle'
import { getLayerWeights } from './layerWeights'

/**
 * Compose la Voie lactée + les 8 galaxies réelles nommées du Groupe Local
 * (Andromède, M33, Nuages de Magellan, Naine du Sagittaire, NGC 6822, IC 10,
 * Leo I) à partir de sprites pré-cuits individuels (cf.
 * scripts/generate_simulated_textures.mjs pour l'historique : une texture
 * partagée à l'échelle du Groupe Local leur faisait perdre toute structure
 * visible, un split par distance créait un doublon visuel — chaque galaxie a
 * maintenant SA PROPRE texture, dimensionnée sur sa propre taille, avec un
 * halo doux qui l'étend au-delà du nuage d'étoiles pour raccorder
 * visuellement avec le layer de densité au-dessus).
 *
 * La Voie lactée elle-même est ici une galaxie comme les autres (distance 0)
 * — sans ça, elle disparaissait complètement dès qu'on dézoomait au-delà de
 * son propre layer "milkyway" (diagnostic du 6 juillet : trou noir au centre
 * alors qu'on voit déjà les galaxies voisines). Elle utilise cependant une
 * opacité différente (cf. GALAXY_OPACITY_MODE) pour ne pas se superposer à
 * la texture "milkyway" détaillée (DensityLayer) pendant le zoom rapproché.
 *
 * Reste un rendu "en direct" par nécessité (position/taille dépendent du
 * zoom courant), mais LÉGER : quelques `drawImage` par frame (un par
 * galaxie visible), pas ~40 000 tracés canvas comme l'ancien rendu
 * étoile-par-étoile.
 */

const SPRITE_MARGIN = 2.8 // GARDER SYNCHRONISÉ avec scripts/generate_simulated_textures.mjs
// GARDER SYNCHRONISÉ avec la valeur affichée par generate_simulated_textures.mjs
// ("radiusMpc de la Voie lactée...").
const MILKYWAY_RADIUS_MPC = 0.01594329

interface CatalogGalaxy {
  name: string | null
  distanceMpc: number
  radiusMpc: number
  angleDeg: number
  brightness: number
  isReal: boolean
}

// Nom catalogue -> fichier sprite. GARDER SYNCHRONISÉ avec SLUG_BY_NAME dans
// scripts/generate_simulated_textures.mjs.
const SLUG_BY_NAME: Record<string, string> = {
  'Andromède (M31)': 'andromede',
  'Triangulum (M33)': 'triangulum',
  'Grand Nuage de Magellan': 'lmc',
  'Petit Nuage de Magellan': 'smc',
  'Naine du Sagittaire': 'sagittaire',
  'NGC 6822': 'ngc6822',
  'IC 10': 'ic10',
  'Leo I': 'leo1',
}

type OpacityMode = 'combined' | 'localgroup-only'

interface SpriteGalaxy {
  slug: string
  distanceMpc: number
  radiusMpc: number
  angleDeg: number
  opacityMode: OpacityMode
}

// La Voie lactée : sa texture "milkyway" détaillée (DensityLayer) couvre
// déjà tout le zoom rapproché — ce sprite ne doit prendre le relais qu'une
// fois qu'on est sorti de cette plage, d'où 'localgroup-only' plutôt que
// 'combined' (qui doublerait l'affichage pendant le zoom rapproché, comme
// LMC/SMC avant leur correctif du 6 juillet).
const MILKYWAY_ENTRY: SpriteGalaxy = {
  slug: 'milkyway',
  distanceMpc: 0,
  radiusMpc: MILKYWAY_RADIUS_MPC,
  angleDeg: 0,
  opacityMode: 'localgroup-only',
}

interface RealGalaxiesLayerProps {
  halfWidthMpc: number
  opacity: number
  style: DensityStyle
  width: number
  height: number
}

export default function RealGalaxiesLayer({ halfWidthMpc, opacity, style, width, height }: RealGalaxiesLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const galaxiesRef = useRef<SpriteGalaxy[] | null>(null)
  const spritesRef = useRef<Record<string, HTMLCanvasElement>>({}) // grayscale source, chargé une fois
  const coloredRef = useRef<Record<string, HTMLCanvasElement>>({}) // recoloré selon le style courant
  const [assetsVersion, setAssetsVersion] = useState(0)

  // Chargement du catalogue + des 9 sprites (8 galaxies réelles + Voie
  // lactée), une seule fois.
  useEffect(() => {
    let cancelled = false
    async function load() {
      const res = await fetch(`${import.meta.env.BASE_URL}data/local_group_catalog.json`)
      const catalog: CatalogGalaxy[] = await res.json()
      const real: SpriteGalaxy[] = catalog
        .filter((g) => g.isReal)
        .map((gal) => ({
          slug: SLUG_BY_NAME[gal.name ?? ''] ?? '',
          distanceMpc: gal.distanceMpc,
          radiusMpc: gal.radiusMpc,
          angleDeg: gal.angleDeg,
          opacityMode: 'combined' as OpacityMode,
        }))
        .filter((g) => g.slug !== '')
      // Voie lactée D'ABORD (dessous) : son halo ne doit jamais recouvrir
      // visuellement une galaxie plus proche dessinée après — cf.
      // diagnostic du 7 juillet (Naine du Sagittaire, à seulement 0.024 Mpc,
      // semblait disparaître derrière le halo de la Voie lactée dessiné
      // par-dessus).
      const all = [MILKYWAY_ENTRY, ...real]
      galaxiesRef.current = all
      await Promise.all(
        all.map(
          (gal) =>
            new Promise<void>((resolve) => {
              const img = new Image()
              img.src = `${import.meta.env.BASE_URL}data/density_realgal_${gal.slug}.png`
              img.onload = () => {
                const off = document.createElement('canvas')
                off.width = img.naturalWidth
                off.height = img.naturalHeight
                off.getContext('2d')!.drawImage(img, 0, 0)
                spritesRef.current[gal.slug] = off
                resolve()
              }
              img.onerror = () => resolve()
            })
        )
      )
      if (!cancelled) setAssetsVersion((v) => v + 1)
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  // Recoloration des sprites (léger : 9 textures de 320x320) quand le style
  // change ou que les assets viennent de charger.
  useEffect(() => {
    const galaxies = galaxiesRef.current
    if (!galaxies) return
    const params = getStyleParamsForLayer('realgalaxy')
    for (const gal of galaxies) {
      const src = spritesRef.current[gal.slug]
      if (!src) continue
      const n = src.width
      const srcCtx = src.getContext('2d')!
      const data = srcCtx.getImageData(0, 0, n, n)
      const out = srcCtx.createImageData(n, n)
      for (let i = 0; i < n * n; i++) {
        const v = Math.pow(data.data[i * 4] / 255, params.gamma)
        const [r, g, b] = colorForValue(v, style)
        out.data[i * 4] = r
        out.data[i * 4 + 1] = g
        out.data[i * 4 + 2] = b
        out.data[i * 4 + 3] = 255
      }
      const canvas = document.createElement('canvas')
      canvas.width = n
      canvas.height = n
      canvas.getContext('2d')!.putImageData(out, 0, 0)
      coloredRef.current[gal.slug] = canvas
    }
    draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style, assetsVersion])

  function draw() {
    const canvas = canvasRef.current
    const galaxies = galaxiesRef.current
    if (!canvas || !galaxies || width < 1 || height < 1) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const W = canvas.width
    const H = canvas.height
    ctx.clearRect(0, 0, W, H)

    const weights = getLayerWeights(halfWidthMpc)
    // 'combined' (les 8 galaxies réelles) : visibles sur toute la plage
    // "environnement proche" (milkyway) + "Groupe Local" (localgroup) — les
    // deux se recouvrent pendant le fondu entre les deux, d'où la somme
    // plutôt qu'un simple max.
    const combinedOpacity = Math.min(1, weights.milkyway + weights.localgroup)
    // 'localgroup-only' (la Voie lactée) : ne prend le relais qu'une fois
    // sortie de la plage rapprochée, où la texture "milkyway" détaillée du
    // DensityLayer suffit déjà.
    const localgroupOnlyOpacity = weights.localgroup
    if (combinedOpacity < 0.003 && localgroupOnlyOpacity < 0.003) return

    const shortSide = Math.min(W, H)
    const scale = shortSide / 2 / halfWidthMpc // px par Mpc
    const originX = W / 2
    const originY = H / 2
    const MIN_SCREEN_RADIUS_PX = 1.2 // plancher pour rester visible même très dézoomé

    for (const gal of galaxies) {
      const sprite = coloredRef.current[gal.slug]
      if (!sprite) continue
      const galaxyOpacity = gal.opacityMode === 'combined' ? combinedOpacity : localgroupOnlyOpacity
      if (galaxyOpacity < 0.003) continue
      const rad = (gal.angleDeg * Math.PI) / 180
      const cx = originX + Math.cos(rad) * gal.distanceMpc * scale
      const cy = originY + Math.sin(rad) * gal.distanceMpc * scale
      const halfSizePx = Math.max(gal.radiusMpc * SPRITE_MARGIN * scale, MIN_SCREEN_RADIUS_PX)
      if (cx < -halfSizePx || cx > W + halfSizePx || cy < -halfSizePx || cy > H + halfSizePx) continue
      ctx.globalAlpha = galaxyOpacity
      ctx.drawImage(sprite, cx - halfSizePx, cy - halfSizePx, halfSizePx * 2, halfSizePx * 2)
    }
    ctx.globalAlpha = 1
  }

  useEffect(() => {
    draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [halfWidthMpc, width, height, assetsVersion])

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
        opacity,
      }}
    />
  )
}
