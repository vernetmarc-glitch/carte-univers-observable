/**
 * Fonctions partagées de cohérence spatio-temporelle — cf. §11.3 du
 * document d'architecture (docs/architecture-univers-observable.md).
 *
 * SOURCE UNIQUE : toute évolution de ces formules doit être reportée ici
 * ET dans le document d'architecture (§11.3/§12), pas recopiée à la main
 * dans chaque prototype ou script de génération.
 *
 * Format volontairement simple (pas de module ES, pas de dépendance) pour
 * être chargeable à la fois :
 *   - côté navigateur : <script src="spacetime-shared.js"></script>
 *     (expose window.SpacetimeShared)
 *   - côté Node hors-ligne (generate_layers.py reste en Python — ce
 *     fichier sert aux scripts .mjs et aux prototypes .html)
 */
;(function (root) {
  'use strict'

  // ───────────────────────────────────────────────────────────────────
  // a) Époque de formation par échelle — a_form(s), cf. §11.3.a
  // Table de points (échelle Mpc -> a_form), interpolée en douceur en
  // log(s). Valeurs ancrées dans la recherche du 8 juillet (redshifts de
  // formation galaxies/amas/toile cosmique).
  // ───────────────────────────────────────────────────────────────────
  const A_FORM_CONTROL_POINTS = [
    { logS: Math.log10(0.01), aForm: 0.20 },   // sprites/galaxies
    { logS: Math.log10(2.4), aForm: 0.20 },    // localgroup (memes objets, echelle galaxie)
    { logS: Math.log10(8.49), aForm: 0.55 },   // l1b (transition)
    { logS: Math.log10(30), aForm: 0.65 },     // l2 (amas)
    { logS: Math.log10(67), aForm: 0.70 },     // l2b
    { logS: Math.log10(150), aForm: 0.92 },    // l3 (toile cosmique)
    { logS: Math.log10(2100), aForm: 0.95 },   // l4b
    { logS: Math.log10(14570), aForm: 1.0 },   // l5 (quasi homogene)
  ]

  function smoothstep(t) {
    t = Math.min(Math.max(t, 0), 1)
    return t * t * (3 - 2 * t)
  }

  function aFormForScaleMpc(scaleMpc) {
    const logS = Math.log10(Math.max(scaleMpc, 1e-6))
    const cps = A_FORM_CONTROL_POINTS
    if (logS <= cps[0].logS) return cps[0].aForm
    if (logS >= cps[cps.length - 1].logS) return cps[cps.length - 1].aForm
    for (let i = 0; i < cps.length - 1; i++) {
      if (logS >= cps[i].logS && logS <= cps[i + 1].logS) {
        const span = cps[i + 1].logS - cps[i].logS
        const t = span !== 0 ? smoothstep((logS - cps[i].logS) / span) : 0
        return cps[i].aForm + (cps[i + 1].aForm - cps[i].aForm) * t
      }
    }
    return cps[cps.length - 1].aForm
  }

  // ───────────────────────────────────────────────────────────────────
  // b) Amplitude de structure — A(s,a), cf. §11.3.b
  // ───────────────────────────────────────────────────────────────────
  function structureAmplitude(scaleMpc, a, halfWidthDexOverride) {
    const aForm = aFormForScaleMpc(scaleMpc)
    // Largeur de transition ADAPTATIVE (pas une valeur fixe) : distance en
    // dex entre a_form(s) et a=1 ("aujourd'hui"). Garantit que A(s, a=1)=1
    // de façon CONTINUE (le palier complet est atteint exactement à a=1),
    // au lieu d'un simple clamp qui créerait un saut brutal juste avant
    // a=1 pour les échelles dont a_form est proche de 1 (l2/l2b/l3...).
    // Plancher (0.05) pour éviter une division par zéro quand a_form=1
    // (l5, quasi aucune transition à faire).
    const halfWidthDex = halfWidthDexOverride || Math.max(-Math.log10(aForm), 0.05)
    if (a >= 1) return 1
    const x = Math.log10(Math.max(a, 1e-6)) - Math.log10(aForm)
    const t = (x + halfWidthDex) / (2 * halfWidthDex)
    return smoothstep(t)
  }

  // ───────────────────────────────────────────────────────────────────
  // c) Couleur de convergence partagée — universeGlowColor(a), cf. §11.3.c
  // bg = fond actuel de l'app (#05050a, UniverseMap.tsx). bright = teinte
  // la plus claire de la palette 'astro' (#fff3d6, colormaps.ts).
  // ───────────────────────────────────────────────────────────────────
  function universeGlowColor(a, exp) {
    exp = exp || 2.2
    const t = Math.pow(Math.min(Math.max(1 - a, 0), 1), exp)
    const bg = [5, 5, 10]
    const bright = [255, 243, 214]
    return [0, 1, 2].map((i) => Math.round(bg[i] + (bright[i] - bg[i]) * t))
  }

  // ───────────────────────────────────────────────────────────────────
  // e) Compression spatiale bornée par la physique — cf. §4.7 et §11.3.e
  // Fondu en S entre 2 et 15 Mpc (zone de transition ou le Groupe Local,
  // lie gravitationnellement, cede la place au flux de Hubble dominant),
  // plutot qu'une coupure nette.
  // ───────────────────────────────────────────────────────────────────
  function compressionStrength(scaleMpc) {
    const logS = Math.log10(Math.max(scaleMpc, 1e-6))
    const lo = Math.log10(2), hi = Math.log10(15)
    return smoothstep((logS - lo) / (hi - lo))
  }
  function effectiveHalfWidthMpc(halfWidthMpc, a, scaleMpc) {
    const strength = compressionStrength(scaleMpc)
    const compressed = halfWidthMpc / Math.max(a, 1e-6)
    return halfWidthMpc + (compressed - halfWidthMpc) * strength
  }

  const SpacetimeShared = {
    aFormForScaleMpc,
    structureAmplitude,
    universeGlowColor,
    compressionStrength,
    effectiveHalfWidthMpc,
    smoothstep,
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = SpacetimeShared
  } else {
    root.SpacetimeShared = SpacetimeShared
  }
})(typeof window !== 'undefined' ? window : globalThis)
