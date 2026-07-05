/**
 * Palettes de couleur pour la couche de densité de matière (Phase 4).
 *
 * La texture source est en niveaux de gris (valeur normalisée 0-1) ;
 * la coloration est appliquée ici, côté client, pour permettre de changer
 * de style instantanément sans regénérer les textures.
 */

export type DensityStyle = 'sober' | 'contrasted' | 'astro'

interface Stop {
  t: number // 0-1
  rgb: [number, number, number]
}

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.replace('#', ''), 16)
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255]
}

function makeStops(hexes: string[]): Stop[] {
  return hexes.map((hex, i) => ({ t: i / (hexes.length - 1), rgb: hexToRgb(hex) }))
}

const PALETTES: Record<DensityStyle, Stop[]> = {
  sober: makeStops(['#03040a', '#0a1a3a', '#2a5aa0', '#8fc7ff', '#f2f8ff']),
  contrasted: makeStops(['#020009', '#1a0a3a', '#5a1a8a', '#c02a7a', '#ff8a3a', '#fff2b0']),
  astro: makeStops(['#000000', '#170a05', '#4a1f0a', '#a8480f', '#e8a13a', '#fff3d6']),
}

export const DENSITY_STYLE_LABELS: Record<DensityStyle, string> = {
  sober: 'Sobre',
  contrasted: 'Contrasté',
  astro: 'Astro',
}

/** Interpole la couleur pour une valeur normalisée t ∈ [0,1] selon le style choisi. */
export function colorForValue(t: number, style: DensityStyle): [number, number, number] {
  const stops = PALETTES[style]
  const clamped = Math.min(Math.max(t, 0), 1)
  let i = 0
  while (i < stops.length - 2 && stops[i + 1].t < clamped) i++
  const a = stops[i]
  const b = stops[i + 1]
  const span = b.t - a.t
  const frac = span > 0 ? (clamped - a.t) / span : 0
  return [
    a.rgb[0] + (b.rgb[0] - a.rgb[0]) * frac,
    a.rgb[1] + (b.rgb[1] - a.rgb[1]) * frac,
    a.rgb[2] + (b.rgb[2] - a.rgb[2]) * frac,
  ]
}

/** Précalcule une table de 256 couleurs pour un style donné (rapide à appliquer pixel par pixel). */
export function buildLookupTable(style: DensityStyle): Uint8ClampedArray {
  const table = new Uint8ClampedArray(256 * 3)
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = colorForValue(i / 255, style)
    table[i * 3] = r
    table[i * 3 + 1] = g
    table[i * 3 + 2] = b
  }
  return table
}
