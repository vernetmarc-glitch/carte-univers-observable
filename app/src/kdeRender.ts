import { colorForValue, type DensityStyle } from './colormaps'

/**
 * Rendu par estimation de densité à noyau (KDE) : chaque galaxie contribue un
 * halo large (gaussien, tendance de densité) + un point central compact
 * (préfigure le rendu "point" qu'aurait cette même galaxie vue de encore
 * plus loin/plus zoomée). Paramètres calibrés visuellement via
 * app/public/glow-test.html — ne pas modifier sans repasser par cet outil.
 */
export const KDE_PARAMS = {
  sizeMpc: 0.59, // sigma du halo
  amplitude: 3.5, // contraste de brillance
  haloScale: 0.35, // luminosité du halo (réduite : trop de halos proches se cumulaient visuellement)
  coreScale: 1.3, // luminosité du point central (réduite — la valeur précédente était trop lumineuse à tous les zooms)
}

// Plage de zoom où le layer Groupe Local domine (cf. layerWeights.ts : LAYER_EDGES_MPC[0..1]).
const LOCALGROUP_LOW_MPC = 0.1
const LOCALGROUP_HIGH_MPC = 2.4
// En zoomant vers la Voie lactée, plusieurs halos proches (Sagittaire, Nuages de
// Magellan...) se superposent et éblouissent la vue. On réduit donc le halo
// (pas le point central, qui doit rester visible) à mesure qu'on approche de 0.1 Mpc.
const HALO_MIN_FACTOR = 0.3

function smoothstep(e0: number, e1: number, x: number): number {
  const t = Math.min(Math.max((x - e0) / (e1 - e0), 0), 1)
  return t * t * (3 - 2 * t)
}

/** Facteur multiplicatif du halo (1 près de L2, HALO_MIN_FACTOR près de la Voie lactée). */
export function haloFadeFactor(halfWidthMpc: number): number {
  const t = smoothstep(Math.log10(LOCALGROUP_LOW_MPC), Math.log10(LOCALGROUP_HIGH_MPC), Math.log10(halfWidthMpc))
  return HALO_MIN_FACTOR + (1 - HALO_MIN_FACTOR) * t
}

export interface KdeGalaxy {
  distanceMpc: number
  angleDeg: number
  brightness: number
}

/**
 * Calcule le champ KDE (résolution n×n) pour un champ de vue de demi-largeur
 * halfWidthMpc, à partir d'une liste de galaxies (distance/angle/brillance).
 */
export function computeKdeField(
  galaxies: KdeGalaxy[],
  halfWidthMpc: number,
  n: number,
  params = KDE_PARAMS
): Float64Array {
  const pixelSizeMpc = (2 * halfWidthMpc) / n
  const coreSigmaMpc = pixelSizeMpc * 1.3
  const field = new Float64Array(n * n)
  const effectiveHaloScale = params.haloScale * haloFadeFactor(halfWidthMpc)

  for (const gal of galaxies) {
    if (gal.distanceMpc > halfWidthMpc * 1.2) continue
    const rad = (gal.angleDeg * Math.PI) / 180
    const gx = Math.cos(rad) * gal.distanceMpc
    const gy = Math.sin(rad) * gal.distanceMpc
    const peakAmp = Math.log(1 + gal.brightness * params.amplitude)
    const cx = Math.round(n / 2 + gx / pixelSizeMpc)
    const cy = Math.round(n / 2 + gy / pixelSizeMpc)

    const haloSpanPx = Math.max(2, Math.ceil((params.sizeMpc * 4) / pixelSizeMpc))
    for (let y = Math.max(0, cy - haloSpanPx); y < Math.min(n, cy + haloSpanPx); y++) {
      for (let x = Math.max(0, cx - haloSpanPx); x < Math.min(n, cx + haloSpanPx); x++) {
        const xMpc = (x - n / 2) * pixelSizeMpc
        const yMpc = (y - n / 2) * pixelSizeMpc
        const d2 = (xMpc - gx) ** 2 + (yMpc - gy) ** 2
        field[y * n + x] += effectiveHaloScale * peakAmp * Math.exp(-d2 / (2 * params.sizeMpc ** 2))
      }
    }

    const coreSpanPx = Math.max(1, Math.ceil((coreSigmaMpc * 4) / pixelSizeMpc))
    for (let y = Math.max(0, cy - coreSpanPx); y < Math.min(n, cy + coreSpanPx); y++) {
      for (let x = Math.max(0, cx - coreSpanPx); x < Math.min(n, cx + coreSpanPx); x++) {
        const xMpc = (x - n / 2) * pixelSizeMpc
        const yMpc = (y - n / 2) * pixelSizeMpc
        const d2 = (xMpc - gx) ** 2 + (yMpc - gy) ** 2
        field[y * n + x] += params.coreScale * peakAmp * Math.exp(-d2 / (2 * coreSigmaMpc ** 2))
      }
    }
  }
  return field
}

/** Référence de normalisation fixe (pas de re-normalisation par frame, pour éviter tout scintillement au zoom/pan). */
export function kdeReferenceMax(params = KDE_PARAMS): number {
  const peakAmp = Math.log(1 + 1 * params.amplitude) // brightness max = 1
  return peakAmp * (params.haloScale + params.coreScale)
}

/** Colorise un champ KDE (Float64Array n×n) en ImageData, selon le style choisi. */
export function colorizeKdeField(field: Float64Array, n: number, style: DensityStyle, vmax: number): ImageData {
  const canvas = document.createElement('canvas')
  canvas.width = n
  canvas.height = n
  const ctx = canvas.getContext('2d')!
  const out = ctx.createImageData(n, n)
  for (let i = 0; i < field.length; i++) {
    const v = Math.min(field[i] / vmax, 1)
    const [r, g, b] = colorForValue(v, style)
    out.data[i * 4] = r
    out.data[i * 4 + 1] = g
    out.data[i * 4 + 2] = b
    out.data[i * 4 + 3] = 255
  }
  return out
}
