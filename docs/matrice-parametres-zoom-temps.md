# Matrice de paramètres zoom × temps — document de référence versionnable

*Créé le 13 juillet 2026 — répond au §11.6 du document d'architecture
(`docs/architecture-univers-observable.md`) : « documenter cette matrice
avant de produire le moindre visuel ».*

## 1. Source de vérité et flux d'ajustement

La matrice canonique est **`app/public/data/spacetime_matrix.json`** —
éditable à la main, versionnée avec le reste du dépôt, et consommée telle
quelle par la génération ET l'affichage (aucun paramètre redéfini ailleurs) :

```
spacetime_matrix.json  ──lu par──▶  scripts/generate_spacetime_frames.py   (cuit les 114 frames st_*.png)
                       ──lu par──▶  scripts/dev/spacetime_pipeline.py       (pipeline headless partagé)
                       ──lu par──▶  scripts/dev/validate_spacetime_matrix.py (validation §13, 119 contrôles)
                       ──lu par──▶  app/public/spacetime-matrix-test.html    (prototype 2 curseurs)
```

**Flux d'ajustement d'un paramètre** :
1. Éditer `spacetime_matrix.json` (jamais les scripts).
2. `cd scripts && python3 generate_spacetime_frames.py` (recuit les frames,
   réécrit le champ `computed` — normalisation figée + tons mesurés).
3. `cd dev && python3 validate_spacetime_matrix.py` (doit afficher
   « TOUTES LES VÉRIFICATIONS PASSENT » avant tout retour visuel, §13).
4. Optionnel mais recommandé après toute modification du prototype :
   `python3 xcheck_dump_ref.py && node xcheck_prototype.mjs` (contrôle
   croisé : le JS du prototype doit reproduire le pipeline Python à ~1e-6).
5. Ouvrir `spacetime-matrix-test.html` pour la confirmation visuelle finale.

`scripts/generate_spacetime_matrix.py` ne sert qu'à reconstruire le JSON
depuis zéro — **le relancer écrase les ajustements manuels**.

## 2. Les deux axes

- **Temps** : la génération reste paramétrée en `a ∈ [1/1101, 1]`
  (recombinaison → aujourd'hui, §3), mais **l'axe d'affichage est le temps
  cosmique LINÉAIRE en milliards d'années** (v2, 13 juillet) :
  `t ∈ [0.000365, 13.7903]` Gyr, sans anamorphose, correspondance
  `a ↔ t ↔ z` lue dans `data/cosmology_table.json` (Planck, H0=67.4).
  Motif : l'ancien curseur `log10(a)` étalait l'embrasement (t < 38 Ma,
  soit 0.3 % de l'âge de l'univers) sur 42 % de la course ; en Gyr linéaire
  il est confiné à 0.31 % de la course, au ras du Big Bang (validé §G).
  Affichage sous le curseur : `t (Ga) · z · a`.
- **Zoom** : demi-champ demandé `∈ [0.02, 14570]` Mpc comobiles
  (bornes de `UniverseMap.tsx`). Le demi-champ EFFECTIF appliqué au rendu
  inclut l'effet d'expansion par échelle (§9 ci-dessous).

### 2.b Nomenclature des cellules (14 juillet, v3 : 13 lignes)

**Principe : un layer de zoom = un visuel unique = un code unique** (si le
sprite change en zoomant, c'est un autre layer). Toute cellule de la matrice
espace-temps × zoom se désigne par un code **`<lettre><chiffre>`** (bloc
`nomenclature` du JSON, montage de validation étiqueté avec ces codes) :

- **Lettre = ligne de zoom**, vue ancrée au `max_mpc` du layer, de la plus
  rapprochée à la plus large :

| Code | A | B | C | D | E | F | G | H | I | J | K | L | M |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Layer | milkyway_hires | milkyway | localgroup | l1b | l2 | l2b | l3 | l3b | l4 | l4a | l4b | l5a | l5 |
| Demi-champ (Mpc) | 0.04 | 0.1 | 2.4 | 8.49 | 30 | 67.08 | 150 | 212.13 | 300 | 793.73 | 2100 | 5531.46 | 14570 |

- **Chiffre = colonne de temps**, 0 → 10, linéaire en Gyr comme le curseur :
  `t_k = 0.000365 + k/10 × 13.79` Ga (0 = recombinaison z≈1100,
  7 ≈ 9.65 Ga soit a≈0.732, 10 = aujourd'hui a=1).

Exemples : `A10` = Voie lactée détaillée aujourd'hui, `M0` = univers
observable à la recombinaison, `D7` = vue l1b (8.49 Mpc) à t≈9.65 Ga.
Résolution programmatique : `spacetime_pipeline.cell_params("D7") → (hw, a)`.

**Règle de permanence des codes** : les lettres sont attribuées une fois
pour toutes ; un layer inséré plus tard prend la première lettre libre
suivante (N, O, …) et c'est la table `zoom_rows` qui donne l'ordre de zoom,
pas l'alphabet — un code désigne donc toujours le même visuel. Décalage
unique effectué le 14/07 (insertion de `milkyway_hires` en A : l'ancien C
= l1b devient D, etc.).

## 3. Colonnes de la matrice, par layer (provenance de chaque valeur)

| Champ | Sens | Provenance |
|---|---|---|
| `max_mpc`, `seed`, `parent`, `margin_factor` | Identiques à la production | `scripts/generate_layers.py` LAYER_SPECS — ne jamais diverger |
| `a_form` | Époque de formation de l'échelle | Points de contrôle §11.4.a (recherche du 8 juillet), interpolés en log(s) |
| `halfwidth_dex`, `center_dex` | Fenêtre de dissolution de `A(s,a)` | §11.4.b + **correctif de continuité du 13 juillet** (cf. §6 ci-dessous) |
| `dissolution_window_a` | `[a_form_effectif², 1]` — bornes où `A` passe de 0 à 1 | Dérivé des deux champs précédents |
| `keyframes_a` | Valeurs de `a` des frames cuites (log-uniformes dans la fenêtre ; queue étendue jusqu'à a=0.04 pour les layers ancrés) | Ce document |
| `anchor_a1` | Paramètres d'ancrage Groupe Local à a=1 | Copie exacte de `generate_layers.py` (itérations des 6-7 juillet) |
| `anchor_scale_mpc` | Échelle pilotant la dissolution de l'ancrage (0.03 Mpc = galaxies) | §11.4.b : « l'ancrage se dissout avec elles » |
| `compression` | Compression 1/a active (flux de Hubble) ou non (système lié) | §11.4.e |
| `residual_bg` (localgroup) | Fond FFT résiduel : amplitude 0.35, seed 31415, VMAX 4.074, cible 8.95/255 | §4.8 (calibré le 10 juillet) — intégré ici, seule différence volontaire à a=1 (§11.7) |
| `uniform_floor` (localgroup) | Convergence vers le ton dissous des layers GRF (129.4/255) | §11.1 point 3 (cohérence de luminosité moyenne) — cf. §7 ci-dessous |

Paramètres globaux : `embrasement` (exp 5, offset 18, ×6, échelle 0.03 —
§11.4.c, calibré le 10 juillet, inchangé), `expansion` (nœuds par échelle,
v2 — §9 ci-dessous), `sprites` + `real_galaxies` (sprites N-corps cuits,
v2 — §10 ci-dessous), `time_axis.display` (axe Gyr — §2),
`nomenclature` (§2.b), `zoom_axis` (frontières/fondus copiés de
`app/src/layerWeights.ts`).

Nouvelle colonne par layer (v2) : `expansion_strength` — effet d'expansion
à l'échelle du layer (cf. §9). Nouveau layer `milkyway` (kind
`sprite_plus_fond`, cf. §10.d). Colonnes/blocs v3 (spécifiés le 14/07, non
cuits — cf. §12) : `filamentarity_ridge_mix` par layer GRF, blocs globaux
`filamentarity`, `tone_mapping`, `field_evolution`, layer `milkyway_hires`
(ligne A) et `real_galaxies.milkyway_hires`.

## 4. Modulations temporelles appliquées à la génération

Pour un layer GRF à l'instant `a` (cf. `generate_spacetime_frames.py`) :

```
champ(a) = ancrage_modulé( champ_base_production × A(s_layer, a),  A_gal(a) )
log_d    = field_to_log_density(champ(a))                      [§11.2 — amplitude AVANT la transformation]
export   = clip((log_d − vmin) / (vmax − vmin))                [vmin/vmax FIGÉS, partagés, §13.3]
```

où `ancrage_modulé` multiplie par `A_gal(a)` : `strength` (donc toutes les
bosses additives ET la profondeur de suppression locale, qui en dépendent
linéairement) et relâche `global_suppression` vers 1
(`gs(a) = 1 − (1−0.35)·A_gal`). À `a=1` : appel strictement identique à la
production (vérifié frame par frame, diff max 0.75/255 = quantification).

Nuance assumée : la « trace » d'ancrage héritée par `l1b` À TRAVERS le champ
parent `l2` (héritage passe-bas de production) est modulée par `A(s_l1b,a)`
et non `A_gal(a)` — effet de second ordre (composante lissée, faible
amplitude), documenté ici pour ne pas être redécouvert.

L'effet d'expansion n'est PAS cuit : la grille comobile est figée (§2),
la fenêtre d'échantillonnage à l'affichage s'élargit en `hw/a` (pondérée par
`expansion_strength(hw)`, cf. §9), et la sélection de layers se fait sur ce
demi-champ effectif — les fondus de zoom existants absorbent naturellement
le changement d'échelle.

## 5. Table évaluée (générée depuis les frames cuites — à régénérer après tout ajustement)

Chaque cellule : `A(s_layer, a)` · moyenne exportée de la frame (/255).
`A_gal` pilote ancrages, sprites et embrasement.

| Layer (s Mpc) | a=1 | a=0.9 | a=0.7 | a=0.5 | a=0.3 | a=0.15 | a=0.05 | a=0.01 | a=0.000908 |
|---|---|---|---|---|---|---|---|---|---|
| **l5** (14570) | A=1.00 · 105 | A=0.56 · 121 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l5a** (5531.46) | A=1.00 · 105 | A=0.56 · 121 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l4b** (2100) | A=1.00 · 105 | A=0.56 · 121 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l4a** (793.73) | A=1.00 · 105 | A=0.56 · 121 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l4** (300) | A=1.00 · 103 | A=0.56 · 120 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l3b** (212.13) | A=1.00 · 102 | A=0.56 · 120 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l3** (150) | A=1.00 · 108 | A=0.56 · 123 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l2b** (67.08) | A=1.00 · 112 | A=0.94 · 115 | A=0.50 · 127 | A=0.00 · 130 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l2** (30) | A=1.00 · 105 | A=0.96 · 107 | A=0.63 · 120 | A=0.10 · 129 | A=0.00 · 130 | A=0.00 · 130 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **l1b** (8.49) | A=1.00 · 127 | A=0.98 · 127 | A=0.79 · 128 | A=0.38 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 | A=0.00 · 129 |
| **localgroup** (2.4) | A=1.00 · 9 | A=1.00 · 9 | A=0.97 · 11 | A=0.88 · 19 | A=0.68 · 41 | A=0.37 · 82 | A=0.01 · 127 | A=0.00 · 129 | A=0.00 · 129 |
| *embrasement (white %)* | 0% | 0% | 0% | 0% | 0% | 0% | 5% | 100% | 100% |
| *A_gal (ancrages/sprites)* | 1.00 | 1.00 | 0.97 | 0.88 | 0.68 | 0.37 | 0.01 | 0.00 | 0.00 |
Lecture : à `a=1`, tous les layers GRF sont à leur rendu de production
(moyennes 104-127) sauf `localgroup` (8.7/255, correctif §4.8) — plus sombre
par design. En remontant le temps, chaque layer converge vers le ton
uniforme partagé **129.4/255** (état dissous, `field_to_log_density(0)` sous
la normalisation figée `vmin=−0.9498, vmax=0.9642`) — y compris
`localgroup` via son plancher (§7). L'embrasement prend ensuite le relais
(nul jusqu'à a≈0.1, 100% à la recombinaison).

## 6. Correctif de continuité de A(s,a) — 13 juillet

La formule §11.4.b avec plancher `w = max(−log10(a_form), 0.05)` centrait la
fenêtre sur `log10(a_form)` : pour les échelles à plancher ACTIF
(`a_form > 10^−0.05 ≈ 0.891`, soit l3 → l5), la fenêtre débordait au-delà de
`a=1` et `A` sautait de 1 à ~0.5 juste sous `a=1` (mesuré : `A(l5, 1−ε) =
0.4995` avec l'ancienne formule) — violation de la contrainte dure « A(s,1)=1
continûment ». Correctif (appliqué dans `spacetime-shared.js`,
`spacetime_pipeline.py`, `validate_fullscene_render.py`) :

```
centre = min(log10(a_form), −w)      [la fenêtre se termine TOUJOURS à a=1]
```

Sans effet pour les échelles où le plancher est inactif (galaxies, l1b, l2,
l2b — rendus déjà calibrés). Conséquence assumée : les fenêtres de l3 → l5
coïncident toutes sur `a ∈ [0.794, 1]` (leurs `a_form` 0.92-1.0 sont plus
proches de 1 que la demi-largeur plancher) — l'échelonnement fin de la toile
cosmique est absorbé par le plancher. Si on veut le restaurer un jour :
réduire le plancher dans la matrice ET revalider la continuité.

## 7. Plancher de convergence de `localgroup`

`localgroup` est exporté LINÉAIREMENT (`clip(champ/4.074)`), pas en
log-densité : sans correction, sa dissolution convergerait vers le noir
(0/255) alors que les layers GRF convergent vers 129.4/255 — exactement la
rupture de luminosité moyenne que §11.1 point 3 interdit. Le plancher
`(1−A_gal(a)) × ton_dissous × 4.074` est un décalage du CHAMP avant export
(même famille de mécanisme que l'embrasement §11.4.c — un paramètre de
génération, pas un calque) : nul à `a=1`, il amène la texture au même état
uniforme que les autres layers quand les galaxies sont dissoutes.
Physiquement : la matière ne disparaît pas, elle s'uniformise.

## 8. Simplifications propres au prototype (à traiter à l'intégration production)

- Le poids de zoom du layer `milkyway` est reporté sur le FOND `localgroup`
  (cf. §10.d) : la Voie lactée y est rendue par son sprite cuit
  (`dissolution_sprites/milkyway_f*.png`), pas par `density_milkyway.png`.
  L'intégration production devra décider du traitement temporel de la
  texture `milkyway` elle-même (probablement le même trio sprite + fond
  ancré + plancher).
- Le fondu entre layers de zoom reste le fondu alpha de production
  (`layerWeights.ts`) — mécanisme d'AXE DE ZOOM existant, distinct de
  l'interdiction §11.3 qui porte sur les transitions temporelles.
- Frames 512×512 (36 Mo pour 114 frames avant optimisation PNG, ~16 Mo
  réels) — résolution/nombre de keyframes réductibles via la matrice si le
  poids devient un problème.

## 9. Effet d'expansion par échelle (v2 — 13 juillet)

Remplace la rampe globale `lo=2/hi=15` Mpc, qui violait le §11.4.e
(force 0.66 à 8.5 Mpc → contraction apparente du champ des 96 galaxies
liées en remontant le temps — problème n°3 du 13 juillet).

- Bloc `expansion.nodes` du JSON : `[[0.03,0], [2.4,0], [8.49,0.15],
  [30,0.65], [67.08,0.9], [150,1.0], [14570,1.0]]` — `strength(hw)`
  interpolé en smoothstep sur `log10(s)` entre les nœuds, piloté par le
  demi-champ DEMANDÉ au curseur.
- `hw_eff = hw + (hw/a − hw) × strength(hw)`.
- Justification physique : ≲2.4 Mpc lié (Groupe Local, aucun effet) ;
  8.5 Mpc dominé visuellement par le volume local découplé (résiduel 0.15,
  validé par Marc) ; ≥150 Mpc flux de Hubble pur.
- Chaque layer porte sa valeur dans la colonne `expansion_strength`
  (redondance de lecture ; la définition fonctionnelle est la courbe des
  nœuds).
- Implémentations synchronisées : `SpacetimeShared.expansionStrengthFromNodes`
  / `effectiveHalfWidthMpcNodes` (JS) et `spacetime_pipeline.expansion_strength`
  / `effective_halfwidth` (Python). Les anciennes fonctions
  `compressionStrength`/`effectiveHalfWidthMpc` ne subsistent que pour les
  anciens prototypes.
- Validation (§E) : `hw_eff` exactement constant à toute échelle ≤2.4 Mpc ;
  `strength(max_mpc)` = valeur matrice pour les 12 layers ; écart apparent
  MW–M31 constant dans le temps (centroïdes, tolérance 3 px couvrant le
  mouvement propre N-corps cuit dans les frames, qui relève de l'accrétion
  et PAS de l'expansion).

## 10. Sprites galactiques N-corps cuits (v2 — 13 juillet)

Corrige les problèmes n°1/4/5/6 du 13 juillet : le prototype v1 utilisait
des splats de particules bruts (points sans morphologie, flux conservé donc
jamais éteints) au lieu des 126 sprites cuits des sessions des 9-10 juillet.

### 10.a Chaîne de génération (bloc `real_galaxies.generation` du JSON)

1. **Simulation** — `scripts/simulate_dissolution.mjs` : N-corps
   Barnes-Hut (θ=0.75), intégrateur leapfrog, softening 0.018 (unités
   rayon=1, équivalent au 900 al/52000 al calibré pour la Voie lactée),
   480 pas, 14 keyframes, 2500 particules/galaxie, conditions initiales =
   morphologies GalaxyModel réelles + composantes de vitesse
   rotationnelles. Sortie : `data/dissolution_keyframes.json`.
2. **Cuisson** — `scripts/generate_dissolution_sprites.mjs` :
   `POINT_SIZE=0.5`, `HALO_GROWTH=8.5` (σ_px = 0.5·(1+progress·7.5)),
   `BLUR_MAX_PX=6` (flou = progress^1.5·6), `FILAMENT_AMOUNT=0.8`
   (bruit multiplicatif en cloche 4·p·(1−p)), ton final `1−exp(−champ)`
   (canal saturant, §11.3), amplitude par particule `0.18+b·0.55`.
   **Cadrage : demi-largeur = maxExtent(dernière frame) × 1.15, FIXE pour
   toutes les frames d'une galaxie** (pas de « zoom » entre frames au
   runtime). `progress = f/13` (linéaire). Sortie : 126 PNG 512² gris,
   `data/dissolution_sprites/{slug}_f00..f13.png` (9 galaxies × 14 frames).

### 10.b Entrées par galaxie (bloc `real_galaxies.entries`)

Positions/angles/rayons du catalogue (`local_group_catalog.json` +
Voie lactée au centre, rayon 0.01594329 Mpc). Champ dérivé stocké :
`sprite_halfwidth_units` = maxExtent(f13)×1.15 (unités de rayon
galactique, recalculable depuis `dissolution_keyframes.json`) et
`sprite_halfwidth_mpc = sprite_halfwidth_units × radius_mpc` — demi-étendue
MONDE de la frame sprite. Valeurs : milkyway 0.1231 Mpc, andromede 0.2430,
triangulum 0.0661, lmc 0.0173, smc 0.0102, sagittaire 0.0117,
ngc6822 0.0076, ic10 0.0058, leo1 0.0036.

### 10.c Rendu runtime (bloc `sprites`)

- `progress = 1 − A_gal(a)` → paire de frames interpolée linéairement
  (`frame = progress × 13`).
- **Extinction : contribution × A_gal(a)^`fade_exponent` avec exposant
  2.0** — décision du 13 juillet : les sprites se dissolvent DANS le fond
  AVANT que le fond (ancrages à A_gal^1) ne se dissolve à son tour.
  Validation empirique (§F) : contraste sprite relatif < contraste fond
  MESURÉ à a∈{0.5, 0.3, 0.15, 0.1} (ex. a=0.15 : 0.274 vs 0.513) ;
  extinction complète à a≤0.04.
- Mélange « screen » (§11.3), jamais de fondu alpha temporel.
- Zone de visibilité : fondu en S sur le demi-champ EFFECTIF,
  `visible_fade_band_mpc = [4, 6]` (aucune apparition brutale en zoomant).
- **Plancher de lisibilité sur le CŒUR** :
  `frame_half_px = max(physique, min_render_core_px × sprite_halfwidth_units)`
  avec `min_render_core_px = 1.25`. Motif : la frame est cadrée sur la
  dispersion finale (~7-9 rayons), le cœur n'en occupe que ~1/7 — un
  plancher sur la frame entière laissait le cœur sous-échantillonné
  (aliasing → naines invisibles, bogue attrapé par la validation §F).
  Léger surdimensionnement des naines assumé aux zooms larges.
- Implémentations synchronisées 1:1 : `compositeSprites` (prototype JS) et
  `spacetime_pipeline.composite_sprites` (Python) — contrôle croisé
  automatique (écarts ≤ 1e-7).

### 10.d Layer `milkyway` (kind `sprite_plus_fond`)

Réintégré le 13 juillet (perdu dans la v1). Aucune frame propre :
sprite `milkyway_f*` au centre + FOND = frames `st_localgroup_*`
échantillonnées sur la fenêtre (le poids de zoom milkyway est reporté sur
localgroup), avec le plancher de convergence §7. Mêmes lois temporelles que
les autres sprites (`a_form` galaxies = 0.20).

## 11. Validation v2 (sections E/F/G/H du validateur)

157 contrôles au 14 juillet : expansion par échelle (E), sprites cuits —
présence des 9 galaxies à a=1, extinction, séquencement empirique
sprites-avant-fond (F), axe de temps Gyr — monotonie, aller-retour exact,
embrasement à 0.31 % de la course (G), nomenclature — couverture,
linéarité, résolution des codes (H). Montage : grille canonique étiquetée
A..L × 0..10 (`scripts/dev/spacetime_matrix_montage.png`). Contrôle croisé
JS/Python : `xcheck_dump_ref.py` + `xcheck_prototype.mjs` (sprites inclus).

## 12. Spécification v3 (14 juillet) — SPÉCIFIÉE, NON GÉNÉRÉE

Quatre évolutions validées par Marc le 14/07 (réponses a/b/c/d), décrites
dans les blocs du JSON listés dans `pending_generation`. Aucune frame ni
texture n'a encore été cuite avec ces paramètres — la table évaluée §5 et
les frames `st_*` restent en état v2.

### 12.a Filamentarité par crêtes — REMPLACÉE (cf. §12.e)

*Les §12.a et 12.c-bis décrivent l'approche par crêtes multi-octaves,
jamais cuite : elle produisait de la mousse cellulaire, pas la toile de la
référence. Remplacée le 16 juillet par le moteur d'advection de Zel'dovich
(§12.e). Conservés pour l'historique.*

### 12.a-archive Filamentarité à a=1 (bloc `filamentarity`, colonnes D→M)

Étape de squelettisation avant `field_to_log_density` : transformée
« ridged » `1−|2n−1|^1.5` mélangée au champ d'origine (`ridge_mix` par
layer : 0.85 sur D..G, décroissant à 0.4 sur M), renforcement HF (0.25),
assombrissement des vides (gamma 1.5). **Contrainte physique (réponse c)** :
la transformée n'est appliquée qu'à la composante passe-bande de longueur
d'onde comobile < **150 Mpc** (`filament_max_scale_mpc`) — la toile
cosmique réelle n'a pas de filaments au-delà ; aux lignes L/M, seuls
subsistent de tout petits filaments (<1 % du cadre) sur un fond
statistiquement uniforme. Mêmes graines et mêmes phases qu'actuellement.
**Implication validée (réponse a)** : les textures de production
`density_l*.png` seront régénérées avec les mêmes paramètres — l'application
principale change d'aspect à a=1, la base de non-régression est rétablie
sur les nouvelles textures, `glow-test.html` resynchronisé à la main.

### 12.b Mapping de ton (bloc `tone_mapping`)

Cible de ton moyen **30–45/255** (réponse b) pour les layers GRF à a=1,
contre ~130/255 actuellement (saut injustifié à la frontière C/D, le
localgroup étant à ~9/255). Gain+gamma post-log-normale ; la filamentarité
fait l'essentiel de la chute. **Cascade obligatoire** : ton uniforme dissous
partagé (129.4/255) et plancher localgroup (×4.074) rescalés par le même
mapping ; embrasement inchangé. Validation : continuité du ton moyen à
travers le fondu C/D à plusieurs temps.

### 12.c Évolution temporelle du champ (bloc `field_evolution`)

Chaque keyframe de chaque layer est **régénérée en FFT avec les mêmes
graines et phases** mais des paramètres dépendant de `a` : filamentarité
relâchée (`ridge_mix × A(s,a)^1.25`), lissage croissant vers le passé
(`σ = (1−A)·0.015·max_mpc`), HF ∝ A, enveloppe d'amplitude A(s,a) v2
conservée. Les filaments se distendent et se dissolvent physiquement
(accrétion à l'envers) au lieu d'un fondu de contraste vers l'uniforme.
Calendriers pilotés par `a_form(s)`/`A(s,a)` (niveau d'accrétion réel au
zoom et temps considérés). Non-régression a=1 par construction. Densité de
keyframes à réévaluer aux zones de morphing rapide.

### 12.c-bis Algorithme de filamentarité v3.1 (15 juillet, calibré en prévisualisation)

Itération après le retour « on ne retrouve pas les filaments de la
référence » : crêtes **multi-octaves en espace pixel** (128/32/8 px,
intersectées avec la coupure 150 Mpc — les lignes L/M ne gardent que les
octaves fines), **modulation par la surdensité grande échelle découplée de
la coupure** (λ > monde/3, héritée du parent : le Vide Local ~30 Mpc existe
même dans le cadre l1b) qui sparsifie la toile et donne la connectivité,
gain de crête 2.6, **renormalisation à variance 1 obligatoire** avant la
log-normale (qui soustrait var/2 — bogue attrapé en preview), et
**suppression ambiante des layers ancrés 0.35 → 1.0** (les galaxies siègent
sur la toile ; la dominance garantie s'adapte). Gamma de ton recalibré
≈ 2.0. Détails exacts : bloc `filamentarity.algorithm_v3_1` du JSON.

### 12.d Voie lactée haute résolution (layer `milkyway_hires`, ligne A)

Nouveau layer de zoom (0.04 Mpc, frontière A/B ajustable) : sprites
**2048²** cuits depuis `milkyway_dissolution_keyframes.json` avec **cadrage
fixe 2 rayons** (mise à jour du 15/07 : le disque occupe ~1024 px de large,
pleine résolution téléphone), splats par particule (`sz` de particleMeta,
amplitude auto-calibrée p99.7→0.95), **apodisation cuite** (fondu cosinus
sur les derniers 6 % du cadre — aucune coupure carrée du débordement, qui
reste assumé car l'extinction A_gal² domine à ce stade). Corrélation
f00/production mesurée en prévisualisation : 0.78. Script
`generate_milkyway_hires_sprites.mjs` à écrire. Absent de `layerWeights.ts`
production pour l'instant.

### 12.e Moteur v3.2 : advection de Zel'dovich (16 juillet — VALIDÉ, variante Z2)

Remplace §12.a/12.c-bis (crêtes) et la log-normale des layers de champ.
Après validation visuelle par Marc de la grille de 10 variantes
(`preview_v3_iter4.py`), la **variante Z2** est gravée : bloc `zeldovich`
du JSON.

- **Génération** : la cascade d'héritage FFT (mêmes graines) produit δ,
  inchangée ; densité = dépôt CIC (grille de masse 1024²) advectée par
  `Ψ̂ = i·k·δ̂/k²`, bande [6 px, **150 Mpc comobiles**] (uniformité K/L/M
  garantie par construction), déplacement rms **S = 11 px** à a=1,
  adoucissement 0.7 px. Exposition `t = (1−exp(−α·ρ^1.6))^1.35`, **α
  global unique** poolé D..M vers 38/255 (rôle de l'ancienne
  normalisation partagée). Colonne par layer : `zeldovich_s_px`.
- **Temps** : une seule loi, `S(s,a) = 11 × A(s,a)^q`, q=1 — Ψ ne change
  jamais, les caustiques se dénouent continûment, à S=0 densité
  exactement uniforme ; ton dissous = `(1−exp(−α))^1.35`, plancher de C
  recalibré, embrasement inchangé. `field_evolution` réécrit sur cette loi.
- **Ancrages (D, trace sur E)** : bosses injectées dans δ AVANT advection
  (le flot se connecte aux galaxies) ; `global_suppression = 1.0` ;
  garantie des maxima re-validée sur la densité déposée.
- **Toile ambiante A/B/C** (bloc `web_ambient`) : texture de la ligne D
  échantillonnée sur la fenêtre courante, mélange screen, amplitudes
  C 0.35 / B 0.20 / A 0.12 (colonnes ajustables) — continuité C/D
  automatique (même toile), diffusion naturelle par upsampling, suit la
  dissolution S(a) de D. Aucune cuisson propre.
- **Recuisson** : textures de production `density_l*.png` + frames `st_*`
  + recalibrages (liste `pending_generation`) ; prévisualisation de
  contrôle obligatoire avant recuisson (bande D10→M10, cellule C avec
  toile ambiante, bande de dissolution H).

### 12.f v3.3 (18 juillet — retours de Marc sur la v3.2 déployée)

Sept retours, quatre familles de correctifs (blocs `zeldovich`,
`galaxy_formation`, `web_ambient`, `prototype_rendering` du JSON) :

1. **Conservation de la luminosité** : α n'est plus global mais **résolu par
   keyframe** pour que le ton moyen de chaque frame vaille exactement
   38/255 — la lumière ne disparaît pas quand les filaments se dissolvent,
   l'état dissous est un fond uni lumineux partagé, l'embrasement part de
   là (l'aplat 33/255 v3.2 passait pour du noir, y compris la ligne M).
2. **Ψ comobile unique** : plus de renormalisation rms par layer — un même
   mode physique déplace la matière identiquement à tous les zooms (les
   caustiques coïncident entre lignes adjacentes, retour n°4). Facteur de
   croissance G global calibré pour reproduire la Z2 validée (rms l3 =
   11 px, stocké dans `computed`). D/E un peu plus effondrés, K..M plus
   uniformes — attendu et souhaité.
3. **Narration de condensation** (`galaxy_formation`, a_form_sprites=0.75) :
   les nuages/filaments (a_form 0.55 de D) apparaissent d'abord, les
   galaxies (sprites, bosses d'ancrage, galaxies procédurales de C) s'y
   condensent ENSUITE (~fenêtre a [0.56, 1]). Le bottom-up réel est
   sciemment écarté ; l'embrasement garde son calage propre.
4. **Prototype** : toile ambiante relevée (0.20/0.35/0.55), moyenne de zone
   en minification (les petits filaments de K/L/M n'étaient pas
   échantillonnés), canvas adaptatif 300→640 px (la Voie lactée hires
   était nette, l'écran ne l'était pas), affichage permanent du code de
   ligne « D · l1b · 8.49 Mpc ».
