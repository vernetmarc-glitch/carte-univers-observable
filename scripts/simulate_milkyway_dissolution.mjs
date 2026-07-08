/**
 * Simule la dispersion physique du disque de la Voie lactée en remontant le
 * temps, via un vrai moteur N-corps (gravité mutuelle, algorithme
 * Barnes-Hut, intégration leapfrog) — pas un flou/bruit procédural.
 *
 * Principe : on part des VRAIES positions d'étoiles de GalaxyModel
 * (aujourd'hui, disque organisé), on leur donne une vitesse de dispersion
 * (radiale + turbulente), et on intègre la gravité mutuelle vers l'AVANT en
 * temps de simulation — ce qui représente le temps qui remonte côté
 * application (frame 0 = aujourd'hui, frame N = état le plus dispersé).
 * La gravité mutuelle, laissée active pendant la dispersion, produit
 * naturellement des amas irréguliers et des filaments (les zones plus
 * denses se regroupent en se dispersant) plutôt qu'une explosion uniforme
 * — cohérent avec la phénoménologie "galaxies grumeleuses" attendue à
 * grand redshift (cf. discussion/recherche du 8 juillet).
 *
 * Sous-échantillonnage à ~6000 particules-traceurs (sur les ~42500
 * étoiles) : Barnes-Hut est testé jusqu'à 100k particules en TEMPS RÉEL
 * dans un navigateur ; hors-ligne en Node, on pourrait pousser bien plus
 * haut, mais 6000 est largement suffisant pour un rendu par nuage de
 * points dense une fois splatté avec un halo à l'affichage, et garde les
 * itérations rapides pendant qu'on calibre la vitesse de dispersion.
 *
 * Sortie : app/public/data/milkyway_dissolution_keyframes.json
 *   { frames: [ { t: number, positions: [[x,y], ...] }, ... ], particleMeta: [{b, sz}, ...] }
 *
 * Usage : node scripts/simulate_milkyway_dissolution.mjs
 */

import { writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'

const GALAXY_MODEL_URL =
  'https://raw.githubusercontent.com/vernetmarc-glitch/le-silence-du-cosmos/main/galaxy-model.js'
const OUT_PATH = new URL('../app/public/data/milkyway_dissolution_keyframes.json', import.meta.url)

const N_TRACERS = 6000
const N_STEPS = 480
const N_KEYFRAMES = 14
const DT = 0.9 // pas de temps (unites arbitraires, calibrees empiriquement avec G/masses ci-dessous)
const G = 1.0
const SOFTENING = 900 // al — evite les forces infinies a courte distance (cf. recherche : "gravitational softening")
const THETA = 0.75 // seuil Barnes-Hut (s/d < theta -> approxime le noeud comme une masse ponctuelle)

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

// ─────────────────────────────────────────────────────────────────────────
// Quadtree Barnes-Hut (2D — coherent avec le reste du projet, la carte
// entiere est un plan galactique/comobile en 2D, pas une simulation 3D).
// ─────────────────────────────────────────────────────────────────────────
class QuadNode {
  constructor(x0, y0, size) {
    this.x0 = x0
    this.y0 = y0
    this.size = size
    this.mass = 0
    this.cx = 0
    this.cy = 0
    this.body = null // particule unique si feuille avec 1 seul corps
    this.children = null
  }

  insert(p) {
    if (this.mass === 0 && !this.children) {
      this.body = p
      this.mass = p.m
      this.cx = p.x
      this.cy = p.y
      return
    }
    if (!this.children) {
      this._subdivide()
      const old = this.body
      this.body = null
      this._insertIntoChild(old)
    }
    this._insertIntoChild(p)
    // met a jour centre de masse cumule
    const newMass = this.mass + p.m
    this.cx = (this.cx * this.mass + p.x * p.m) / newMass
    this.cy = (this.cy * this.mass + p.y * p.m) / newMass
    this.mass = newMass
  }

  _subdivide() {
    const h = this.size / 2
    this.children = [
      new QuadNode(this.x0, this.y0, h),
      new QuadNode(this.x0 + h, this.y0, h),
      new QuadNode(this.x0, this.y0 + h, h),
      new QuadNode(this.x0 + h, this.y0 + h, h),
    ]
  }

  _insertIntoChild(p) {
    const h = this.size / 2
    const idx = (p.x >= this.x0 + h ? 1 : 0) + (p.y >= this.y0 + h ? 2 : 0)
    this.children[idx].insert(p)
  }

  computeForce(p, theta, softening2, g) {
    if (this.mass === 0) return [0, 0]
    if (this.body === p) return [0, 0]
    const dx = this.cx - p.x
    const dy = this.cy - p.y
    const dist2 = dx * dx + dy * dy + softening2
    if (this.body || this.size * this.size < theta * theta * dist2) {
      const dist = Math.sqrt(dist2)
      const f = (g * this.mass) / (dist2 * dist)
      return [f * dx, f * dy]
    }
    let fx = 0
    let fy = 0
    for (const c of this.children) {
      const [cfx, cfy] = c.computeForce(p, theta, softening2, g)
      fx += cfx
      fy += cfy
    }
    return [fx, fy]
  }
}

function buildTree(particles) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of particles) {
    if (p.x < minX) minX = p.x
    if (p.x > maxX) maxX = p.x
    if (p.y < minY) minY = p.y
    if (p.y > maxY) maxY = p.y
  }
  const size = Math.max(maxX - minX, maxY - minY) * 1.05 + 1
  const root = new QuadNode(minX - size * 0.02, minY - size * 0.02, size)
  for (const p of particles) root.insert(p)
  return root
}

// ─────────────────────────────────────────────────────────────────────────
async function main() {
  const GalaxyModel = await loadGalaxyModel()
  const allStars = GalaxyModel.generateGalaxy()
  console.log(`GalaxyModel: ${allStars.length} étoiles générées (MW_R=${GalaxyModel.MW_R} al)`)

  const rng = mulberry32(20260708)
  const step = allStars.length / N_TRACERS
  const tracers = []
  for (let i = 0; i < N_TRACERS; i++) {
    const star = allStars[Math.floor(i * step)]
    tracers.push(star)
  }

  const MW_R = GalaxyModel.MW_R
  const particles = tracers.map((star) => {
    const x = star.gx
    const y = star.gy * GalaxyModel.YSCALE
    const r = Math.sqrt(x * x + y * y) || 1
    // Vitesse de dispersion : composante radiale sortante (proportionnelle
    // a la distance au centre, comme un flot d'expansion local) + une
    // composante turbulente aleatoire (pour casser la symetrie parfaite et
    // laisser la gravite mutuelle former des amas plutot qu'une coquille
    // spherique uniforme).
    const radialSpeed = r * 0.0042
    const turbAngle = rng() * Math.PI * 2
    const turbSpeed = (0.25 + rng() * 0.75) * 520
    return {
      x, y,
      vx: (x / r) * radialSpeed + Math.cos(turbAngle) * turbSpeed,
      vy: (y / r) * radialSpeed + Math.sin(turbAngle) * turbSpeed,
      m: 0.35 + star.b * 1.2, // les etoiles brillantes/du bulbe pesent un peu plus -> restent structurantes
      b: star.b,
      sz: star.sz,
    }
  })

  const softening2 = SOFTENING * SOFTENING
  const keyframeEvery = Math.round(N_STEPS / (N_KEYFRAMES - 1))
  const frames = []

  for (let step_i = 0; step_i <= N_STEPS; step_i++) {
    if (step_i % keyframeEvery === 0 || step_i === N_STEPS) {
      frames.push({
        step: step_i,
        positions: particles.map((p) => [Math.round(p.x), Math.round(p.y)]),
      })
      console.log(`frame @ step ${step_i} (${frames.length}/${N_KEYFRAMES})`)
    }
    if (step_i === N_STEPS) break

    const tree = buildTree(particles)
    const forces = particles.map((p) => tree.computeForce(p, THETA, softening2, G))
    // Leapfrog (kick-drift) — cf. recherche : preserve mieux l'energie sur
    // de nombreux pas qu'un Euler simple.
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      const [fx, fy] = forces[i]
      const ax = (fx * 150000) / p.m // echelle empirique (unites arbitraires calibrees visuellement)
      const ay = (fy * 150000) / p.m
      p.vx += ax * DT
      p.vy += ay * DT
      p.x += p.vx * DT
      p.y += p.vy * DT
    }
  }

  const output = {
    mwRadiusLy: MW_R,
    yscale: GalaxyModel.YSCALE,
    nSteps: N_STEPS,
    frames,
    particleMeta: particles.map((p) => ({ b: p.b, sz: p.sz })),
  }
  writeFileSync(OUT_PATH, JSON.stringify(output))
  console.log(`\n-> ${OUT_PATH}`)
  console.log(`Taille: ${(JSON.stringify(output).length / 1024 / 1024).toFixed(2)} Mo`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
