/**
 * Chargement et mise en cache partagés de GalaxyModel (cf. index.html pour le
 * script CDN). Un seul appel à generateGalaxy() pour toute l'application —
 * évite de recalculer deux fois le même scatter d'étoiles (coûteux) et
 * garantit que la Voie lactée a rigoureusement la même forme partout où elle
 * est dessinée (layer "Voie lactée" ET layer "Groupe Local").
 */

export interface GalaxyStar {
  gx: number
  gy: number
  b: number
  sz: number
}

export interface GalaxyModelApi {
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

let cachedStars: GalaxyStar[] | null = null

/** Appelle le callback dès que GalaxyModel + les étoiles générées sont prêts (une seule fois, mis en cache). */
export function onGalaxyReady(callback: (stars: GalaxyStar[], gm: GalaxyModelApi) => void): () => void {
  let cancelled = false

  function tryInit() {
    if (cancelled) return
    if (window.GalaxyModel) {
      if (!cachedStars) cachedStars = window.GalaxyModel.generateGalaxy()
      callback(cachedStars, window.GalaxyModel)
    } else {
      setTimeout(tryInit, 100)
    }
  }
  tryInit()

  return () => {
    cancelled = true
  }
}
