import { useEffect, useMemo, useState } from 'react'
import {
  ageOfUniverseGyr,
  densityDilutionFactor,
  interpolateAtTime,
  loadCosmologyTable,
  minAgeGyr,
  type CosmologyTable,
} from './cosmology'

function fmt(n: number, digits = 3): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString('fr-FR', { maximumFractionDigits: 0 })
  return n.toLocaleString('fr-FR', { maximumFractionDigits: digits })
}

export default function App() {
  const [table, setTable] = useState<CosmologyTable | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tGyr, setTGyr] = useState(13.8)

  useEffect(() => {
    loadCosmologyTable()
      .then((t) => {
        setTable(t)
        setTGyr(ageOfUniverseGyr(t)) // curseur positionné sur "aujourd'hui" par défaut
      })
      .catch((e) => setError(String(e)))
  }, [])

  const state = useMemo(() => (table ? interpolateAtTime(table, tGyr) : null), [table, tGyr])

  if (error) {
    return <div style={{ color: '#f66', padding: 24, fontFamily: 'monospace' }}>Erreur : {error}</div>
  }
  if (!table || !state) {
    return <div style={{ color: '#ccc', padding: 24, fontFamily: 'monospace' }}>Chargement de la table cosmologique…</div>
  }

  const tMin = minAgeGyr(table)
  const tMax = ageOfUniverseGyr(table)

  // --- Aperçu SVG des trois sphères (échelle relative, PAS le moteur de zoom final) ---
  // On normalise par le plus grand des trois rayons à l'instant courant pour que
  // ça reste lisible quel que soit l'instant choisi sur le curseur.
  const maxRadius = Math.max(state.chiParticleComovingMpc, state.rHubbleComovingMpc, state.chiEventComovingMpc)
  const svgSize = 320
  const scale = (svgSize / 2 - 10) / maxRadius
  const spheres = [
    { label: 'Horizon des particules', radius: state.chiParticleComovingMpc, color: '#5aa9e6' },
    { label: 'Horizon des événements', radius: state.chiEventComovingMpc, color: '#e6a15a' },
    { label: 'Sphère de Hubble', radius: state.rHubbleComovingMpc, color: '#e65a8f' },
  ].sort((a, b) => b.radius - a.radius) // la plus grande dessinée en premier

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', color: '#eee', background: '#05050a', minHeight: '100vh', padding: 24 }}>
      <h1 style={{ fontSize: 20, fontWeight: 600 }}>Carte de l'univers observable — Phase 1 : moteur cosmologique</h1>
      <p style={{ color: '#999', maxWidth: 640, fontSize: 14 }}>
        Outil de debug pour valider le moteur cosmologique avant de construire le rendu final de la carte
        (grille comobile, zoom, layers de densité). Comparez les valeurs ci-dessous à celles du document
        d'architecture (§3.4 et §3.6).
      </p>

      <div style={{ margin: '24px 0' }}>
        <label style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>
          Curseur temporel — âge de l'univers : <strong>{fmt(tGyr, 4)} Ga</strong> (z = {fmt(state.z, 3)})
        </label>
        <input
          type="range"
          min={tMin}
          max={tMax}
          step={(tMax - tMin) / 2000}
          value={tGyr}
          onChange={(e) => setTGyr(Number(e.target.value))}
          style={{ width: '100%', maxWidth: 640 }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', maxWidth: 640, fontSize: 11, color: '#777' }}>
          <span>Recombinaison ({fmt(tMin, 5)} Ga)</span>
          <span>Aujourd'hui ({fmt(tMax, 3)} Ga)</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
          <tbody>
            <Row label="Facteur d'échelle a(t)" value={state.a.toExponential(4)} />
            <Row label="Redshift z" value={fmt(state.z, 3)} />
            <Row label="Dilution densité (1/a³)" value={fmt(densityDilutionFactor(state.a), 2)} />
            <SectionRow label="Horizon des particules" />
            <Row label="Rayon comobile" value={`${fmt(state.chiParticleComovingMpc)} Mpc`} />
            <Row label="Rayon propre (distance actuelle)" value={`${fmt(state.chiParticleProperGly, 3)} Gal`} />
            <SectionRow label="Sphère de Hubble" />
            <Row label="Rayon comobile" value={`${fmt(state.rHubbleComovingMpc)} Mpc`} />
            <Row label="Rayon propre" value={`${fmt(state.rHubbleProperGly, 3)} Gal`} />
            <SectionRow label="Horizon des événements" />
            <Row label="Rayon comobile" value={`${fmt(state.chiEventComovingMpc)} Mpc`} />
            <Row label="Rayon propre" value={`${fmt(state.chiEventProperGly, 3)} Gal`} />
          </tbody>
        </table>

        <div>
          <svg width={svgSize} height={svgSize} style={{ background: '#0a0a14', borderRadius: 8 }}>
            <circle cx={svgSize / 2} cy={svgSize / 2} r={2} fill="#fff" />
            {spheres.map((s) => (
              <circle
                key={s.label}
                cx={svgSize / 2}
                cy={svgSize / 2}
                r={Math.max(s.radius * scale, 1)}
                fill="none"
                stroke={s.color}
                strokeWidth={1.5}
              />
            ))}
          </svg>
          <div style={{ fontSize: 11, marginTop: 8 }}>
            {spheres.map((s) => (
              <div key={s.label} style={{ color: s.color }}>
                ● {s.label}
              </div>
            ))}
          </div>
          <p style={{ fontSize: 11, color: '#666', maxWidth: 320 }}>
            Aperçu à échelle relative (auto-ajustée), pas encore la grille comobile fixe finale —
            ce sera l'objet de la Phase 2.
          </p>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <td style={{ padding: '3px 16px 3px 0', color: '#999' }}>{label}</td>
      <td style={{ padding: '3px 0', fontFamily: 'monospace' }}>{value}</td>
    </tr>
  )
}

function SectionRow({ label }: { label: string }) {
  return (
    <tr>
      <td colSpan={2} style={{ paddingTop: 14, paddingBottom: 4, fontWeight: 600, color: '#ccc' }}>
        {label}
      </td>
    </tr>
  )
}
