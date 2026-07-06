import { useEffect, useRef, useState } from 'react'

export interface CatalogGalaxy {
  name: string | null
  distanceMpc: number
  radiusMpc: number
  angleDeg: number
  brightness: number
  isReal: boolean
}

let cachedRealGalaxies: CatalogGalaxy[] | null = null
let inFlight: Promise<CatalogGalaxy[]> | null = null

function fetchRealGalaxies(): Promise<CatalogGalaxy[]> {
  if (cachedRealGalaxies) return Promise.resolve(cachedRealGalaxies)
  if (inFlight) return inFlight
  inFlight = fetch(`${import.meta.env.BASE_URL}data/local_group_catalog.json`)
    .then((res) => res.json())
    .then((catalog: CatalogGalaxy[]) => {
      const real = catalog.filter((g) => g.isReal)
      cachedRealGalaxies = real
      return real
    })
  return inFlight
}

/** Catalogue des galaxies RÉELLES du Groupe Local (Andromède, M33, Nuages de
 * Magellan...) — source unique partagée entre LocalGroupLayer et
 * MilkyWayLayer, pour qu'elles restent visibles de façon cohérente à toutes
 * les échelles où elles sont physiquement pertinentes, pas seulement sur un
 * seul layer. */
export function useRealGalaxyCatalog(): CatalogGalaxy[] | null {
  const [catalog, setCatalog] = useState<CatalogGalaxy[] | null>(cachedRealGalaxies)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    if (!cachedRealGalaxies) {
      fetchRealGalaxies().then((real) => {
        if (mountedRef.current) setCatalog(real)
      })
    }
    return () => {
      mountedRef.current = false
    }
  }, [])

  return catalog
}
