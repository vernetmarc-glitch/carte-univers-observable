/**
 * Généralise simulate_milkyway_dissolution.mjs aux 9 sprites de
 * RealGalaxiesLayer.tsx (Voie lactée + les 8 galaxies réelles nommées) —
 * même moteur N-corps (Barnes-Hut, leapfrog, softening), mêmes constantes
 * de rotation/dispersion pour tous, en travaillant en UNITÉS NORMALISÉES
 * (position exprimée en multiple du rayon propre de la galaxie, pas en
 * al/Mpc) : ça permet de réutiliser exactement les mêmes réglages
 * physiques (calibrés sur la Voie lactée le 8 juillet) pour les 8 autres,
 * qui ont des tailles réelles très différentes.
 *
 * La Voie lactée utilise les VRAIES étoiles de GalaxyModel (comme avant),
 * normalisées par MW_R. Les 8 autres utilisent le même générateur de
 * morphologie procédurale que generate_simulated_textures.mjs
 * (generateNearbyGalaxyStars, PORT volontaire — cf. avertissement dans ce
 * fichier — à maintenir synchronisé).
 *
 * Sortie : app/public/data/dissolution_keyframes.json
 *   { [slug]: { nSteps, frames: [{step, positions:[[x,y],...]}], particleMeta: [{b}] } }
 *   positions en unités normalisées (1 = rayon propre de la galaxie).
 *
 * Usage : node scripts/simulate_dissolution.mjs
 */

import { writeFileSync, readFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'

const GALAXY_MODEL_URL =
  'https://raw.githubusercontent.com/vernetmarc-glitch/le-silence-du-cosmos/main/galaxy-model.js'
const CATALOG_PATH = new URL('../app/public/data/local_group_catalog.json', import.meta.url)
const OUT_PATH = new URL('../app/public/data/dissolution_keyframes.json', import.meta.url)

const N_TRACERS = 2500
const N_STEPS = 480
const N_KEYFRAMES = 14
const DT = 0.9
const G = 1.0
const SOFTENING = 0.018 // en unites normalisees (rayon=1) ; equivalent relatif au softening calibre pour MW (900 al / 52000 al ~ 0.017)
const THETA = 0.75
// Corrige le 8 juillet : le multiplicateur empirique de la Voie lactee
// (150000) etait calibre en unites ABSOLUES (annees-lumiere, MW_R~52000).
// En unites normalisees (rayon propre = 1), la meme dynamique physique
// demande de diviser ce multiplicateur par MW_R^3 (1x pour l'acceleration
// elle-meme, 2x de plus car la force va comme 1/dist^2 et dist est aussi
// normalise) — sans cette correction, la simulation explosait
// numeriquement (rayon median atteignant des centaines de milliers au
// lieu de ~2).
const ACCEL_SCALE = 150000 / Math.pow(52000, 3)

const SLUG_BY_NAME = {
  'Andromède (M31)': 'andromede',
  'Triangulum (M33)': 'triangulum',
  'Grand Nuage de Magellan': 'lmc',
  'Petit Nuage de Magellan': 'smc',
  'Naine du Sagittaire': 'sagittaire',
  'NGC 6822': 'ngc6822',
  'IC 10': 'ic10',
  'Leo I': 'leo1',
}

// ─────────────────────────────────────────────────────────────────────────
async function loadGalaxyModel() {
  const res = await fetch(GALAXY_MODEL_URL)
  if (!res.ok) throw new Error(`Échec du téléchargement de galaxy-model.js : HTTP ${res.status}`)
  const code = await res.text()
  const dir = mkdtempSync(path.join(tmpdir(), 'galaxy-model-'))
  const file = path.join(dir, 'galaxy-model.cjs')
  writeFileSync(file, code)
  const require = createRequire(import.meta.url)
  return require(file)
}

function mulberry32(seed) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Port de generateNearbyGalaxyStars (generate_simulated_textures.mjs) —
// garder synchronise si l'original change.
const MORPHOLOGY_BY_NAME = {
  'Andromède (M31)': 'spiral',
  'Triangulum (M33)': 'spiral',
  'Grand Nuage de Magellan': 'barred',
  'Petit Nuage de Magellan': 'irregular_wing',
  'Naine du Sagittaire': 'elliptical_stream',
}
function morphologyFor(name) {
  return MORPHOLOGY_BY_NAME[name] ?? 'irregular'
}
function generateMorphologyStars(name, count, seed) {
  const rng = mulberry32(seed)
  const morphology = morphologyFor(name)
  const stars = []
  const radius = 1
  const flatten =
    morphology === 'spiral' ? 0.38 : morphology === 'barred' ? 0.5 : morphology === 'elliptical_stream' ? 0.42 : 0.7
  for (let i = 0; i < count; i++) {
    const u = rng()
    let r = radius * Math.sqrt(-Math.log(1 - u * 0.98)) * 0.55
    r = Math.min(r, radius * 1.3)
    let theta = rng() * Math.PI * 2
    if (morphology === 'spiral') {
      theta += 2.6 * Math.log(r / radius + 0.15) + (rng() - 0.5) * 0.7
    } else if (morphology === 'barred') {
      if (rng() < 0.45) {
        const along = (rng() * 2 - 1) * radius * 0.85
        const across = (rng() - 0.5) * radius * 0.18
        stars.push({ x: along, y: across * flatten, b: 0.4 + rng() * 0.5 })
        continue
      }
      theta += 1.1 * Math.log(r / radius + 0.2) + (rng() - 0.5) * 1.4
    } else if (morphology === 'irregular_wing') {
      if (rng() < 0.25) {
        const wingDir = 0.6
        const wingR = radius * (0.9 + rng() * 0.9)
        const spread = (rng() - 0.5) * radius * 0.4
        stars.push({
          x: wingR * Math.cos(wingDir) - spread * Math.sin(wingDir),
          y: (wingR * Math.sin(wingDir) + spread * Math.cos(wingDir)) * flatten,
          b: 0.2 + rng() * 0.4,
        })
        continue
      }
      theta += (rng() - 0.5) * 2.2
    } else if (morphology === 'elliptical_stream') {
      r = radius * Math.pow(rng(), 0.7)
    }
    const b = morphology === 'elliptical_stream' ? 0.35 + rng() * 0.35 : 0.25 + rng() * 0.55
    stars.push({ x: r * Math.cos(theta), y: r * Math.sin(theta) * flatten, b })
  }
  return stars
}

// ─────────────────────────────────────────────────────────────────────────
// Quadtree Barnes-Hut (identique a simulate_milkyway_dissolution.mjs)
// ─────────────────────────────────────────────────────────────────────────
class QuadNode {
  constructor(x0, y0, size) {
    this.x0 = x0; this.y0 = y0; this.size = size
    this.mass = 0; this.cx = 0; this.cy = 0
    this.body = null; this.children = null
  }
  insert(p) {
    if (this.mass === 0 && !this.children) { this.body = p; this.mass = p.m; this.cx = p.x; this.cy = p.y; return }
    if (!this.children) { this._subdivide(); const old = this.body; this.body = null; this._insertIntoChild(old) }
    this._insertIntoChild(p)
    const newMass = this.mass + p.m
    this.cx = (this.cx * this.mass + p.x * p.m) / newMass
    this.cy = (this.cy * this.mass + p.y * p.m) / newMass
    this.mass = newMass
  }
  _subdivide() {
    const h = this.size / 2
    this.children = [
      new QuadNode(this.x0, this.y0, h), new QuadNode(this.x0 + h, this.y0, h),
      new QuadNode(this.x0, this.y0 + h, h), new QuadNode(this.x0 + h, this.y0 + h, h),
    ]
  }
  _insertIntoChild(p) {
    const h = this.size / 2
    const idx = (p.x >= this.x0 + h ? 1 : 0) + (p.y >= this.y0 + h ? 2 : 0)
    this.children[idx].insert(p)
  }
  computeForce(p, theta, softening2, g) {
    if (this.mass === 0 || this.body === p) return [0, 0]
    const dx = this.cx - p.x, dy = this.cy - p.y
    const dist2 = dx * dx + dy * dy + softening2
    if (this.body || this.size * this.size < theta * theta * dist2) {
      const dist = Math.sqrt(dist2)
      const f = (g * this.mass) / (dist2 * dist)
      return [f * dx, f * dy]
    }
    let fx = 0, fy = 0
    for (const c of this.children) { const [cfx, cfy] = c.computeForce(p, theta, softening2, g); fx += cfx; fy += cfy }
    return [fx, fy]
  }
}
function buildTree(particles) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of particles) {
    if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x
    if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y
  }
  const size = Math.max(maxX - minX, maxY - minY) * 1.05 + 1e-6
  const root = new QuadNode(minX - size * 0.02, minY - size * 0.02, size)
  for (const p of particles) root.insert(p)
  return root
}

// ─────────────────────────────────────────────────────────────────────────
// Simulation generique (unites normalisees, rayon propre = 1) — memes
// constantes de rotation/dispersion que la Voie lactee (calibrees le 8
// juillet), reutilisees telles quelles pour toutes les galaxies.
// ─────────────────────────────────────────────────────────────────────────
function runSimulation(basePoints, seedOffset) {
  const rng = mulberry32(seedOffset)
  const particles = basePoints.map((pt) => {
    const r = Math.sqrt(pt.x * pt.x + pt.y * pt.y) || 1e-4
    const radialSpeed = r * 0.0042
    const turbAngle = rng() * Math.PI * 2
    const turbSpeed = (0.25 + rng() * 0.75) * 0.01 // normalise (~520/52000 = 0.01, meme ratio que MW)
    const tangentialSpeed = r * 0.0034
    const tx = -pt.y / r, ty = pt.x / r
    return {
      x: pt.x, y: pt.y,
      vx: (pt.x / r) * radialSpeed + Math.cos(turbAngle) * turbSpeed + tx * tangentialSpeed,
      vy: (pt.y / r) * radialSpeed + Math.sin(turbAngle) * turbSpeed + ty * tangentialSpeed,
      m: 0.35 + pt.b * 1.2,
      b: pt.b,
    }
  })

  const softening2 = SOFTENING * SOFTENING
  const keyframeEvery = Math.round(N_STEPS / (N_KEYFRAMES - 1))
  const frames = []

  for (let step_i = 0; step_i <= N_STEPS; step_i++) {
    if (step_i % keyframeEvery === 0 || step_i === N_STEPS) {
      frames.push({ step: step_i, positions: particles.map((p) => [p.x, p.y]) })
    }
    if (step_i === N_STEPS) break
    const tree = buildTree(particles)
    const forces = particles.map((p) => tree.computeForce(p, THETA, softening2, G))
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      const [fx, fy] = forces[i]
      // Echelle empirique normalisee (equivalent du 150000/MW_R^? utilise
      // en unites al pour la Voie lactee, reexprime ici en unites rayon=1).
      // BUG CORRIGE (8 juillet) : cf. definition de ACCEL_SCALE en tete de fichier.
      const ax = (fx * ACCEL_SCALE) / p.m
      const ay = (fy * ACCEL_SCALE) / p.m
      p.vx += ax * DT; p.vy += ay * DT
      p.x += p.vx * DT; p.y += p.vy * DT
    }
  }

  return { nSteps: N_STEPS, frames, particleMeta: particles.map((p) => ({ b: p.b })) }
}

// ─────────────────────────────────────────────────────────────────────────
async function main() {
  const result = {}

  const GalaxyModel = await loadGalaxyModel()
  const allStars = GalaxyModel.generateGalaxy()
  const step = allStars.length / N_TRACERS
  const mwPoints = []
  for (let i = 0; i < N_TRACERS; i++) {
    const star = allStars[Math.floor(i * step)]
    mwPoints.push({ x: star.gx / GalaxyModel.MW_R, y: (star.gy * GalaxyModel.YSCALE) / GalaxyModel.MW_R, b: star.b })
  }
  console.log('Simulation Voie lactée...')
  result.milkyway = runSimulation(mwPoints, 20260708)
  console.log(`  -> ${result.milkyway.frames.length} frames`)

  const catalog = JSON.parse(readFileSync(CATALOG_PATH, 'utf8'))
  for (const gal of catalog) {
    if (!gal.isReal) continue
    const slug = SLUG_BY_NAME[gal.name]
    if (!slug) continue
    console.log(`Simulation ${gal.name} (${slug})...`)
    const seed = (gal.name.length + 1) * 7919
    const points = generateMorphologyStars(gal.name, N_TRACERS, seed).map((s) => ({ x: s.x, y: s.y, b: s.b }))
    result[slug] = runSimulation(points, seed + 1)
    console.log(`  -> ${result[slug].frames.length} frames, ${points.length} particules`)
  }

  writeFileSync(OUT_PATH, JSON.stringify(result))
  console.log(`\n-> ${OUT_PATH}`)
  console.log(`Taille: ${(JSON.stringify(result).length / 1024 / 1024).toFixed(2)} Mo`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
