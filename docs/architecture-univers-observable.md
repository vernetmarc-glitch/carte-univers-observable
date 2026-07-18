# Architecture — Carte interactive de l'univers observable
### Document de référence technique et scientifique
Version 1.0 — Juillet 2026

---

## 0. État actuel du projet — résumé pour reprise de contexte

*(Section mise à jour le 7 juillet 2026, pensée pour permettre à Claude de reprendre ce projet dans une nouvelle conversation sans relire tout l'historique. Décrit l'état ACTUEL et son rationnel — pas l'historique des étapes pour y arriver.)*

**Dépôt et déploiement**
- Dépôt : `vernetmarc-glitch/lheure-de-senivrer` (renommé depuis `carte-univers-observable`)
- Site en ligne : https://vernetmarc-glitch.github.io/lheure-de-senivrer/
- Outils de calibration : `glow-test.html` (style/couleur des textures de densité) et `l1b-anchor-test.html` (halo/bruit de fond de l'ancrage du Groupe Local sur `l1b`) — cf. §4.7
- Déploiement automatique via GitHub Actions (`.github/workflows/deploy.yml`) sur push vers `main`
- Projet installable en PWA (`manifest.json`, icônes générées depuis le logo fourni), nom affiché "L'Heure de s'enivrer"

**Architecture de rendu actuelle**
- App plein écran (pas d'onglets, pas de légendes texte) : titre en haut à gauche, bouton réglages (⚙) en haut à droite (style + présence du fond), curseur de zoom vertical à droite, curseur de temps horizontal en bas — tous en overlay sur la carte, avec `env(safe-area-inset-*)`.
- Zone de rendu clampée à un ratio max de 2,4:1 (bandes noires fixes au-delà) pour éviter qu'un layer ne "disparaisse" sur écrans très larges/étroits.
- Canvas dimensionnés selon `devicePixelRatio` (plafonné à 3) pour la netteté sur écrans Retina.
- Chargement des textures progressif et priorisé (le layer du zoom courant en premier, affichage dès l'arrivée de chaque texture), avec indicateur discret en bas à droite.
- **Principe général de performance retenu** : tout ce qui PEUT être pré-calculé hors-ligne (Node/Python) et livré sous forme de bitmap L'EST, plutôt que d'être recalculé à chaque frame côté client. Les seuls rendus encore "en direct" (RealGalaxiesLayer, cf. §4.6) le sont par nécessité (position/taille dépendent du zoom courant), mais restent légers : quelques `drawImage`, jamais de génération procédurale ni de boucle sur des milliers d'éléments par frame.

**Les layers, du plus proche au plus lointain**

1. **`milkyway`** (`DensityLayer.tsx`, texture `density_milkyway.png`) : disque + bulbe de la Voie lactée UNIQUEMENT (pas les galaxies voisines, cf. point 2). Généré hors-ligne en exécutant le vrai module partagé `GalaxyModel` (récupéré depuis le dépôt `le-silence-du-cosmos` au moment de la génération, jamais réimplémenté localement) — cf. `scripts/generate_simulated_textures.mjs`. N'est plus chargé côté client en JavaScript : seul le résultat pré-cuit (bitmap) est livré à l'app.

2. **`RealGalaxiesLayer`** (composant React séparé, `app/src/RealGalaxiesLayer.tsx`, PAS une entrée de `DensityLayer`) : compose au runtime 9 sprites pré-cuits individuels — la Voie lactée elle-même (pour rester visible même une fois sortie du zoom rapproché du point 1) + les 8 galaxies réelles nommées du Groupe Local (Andromède, Triangulum/M33, Grand/Petit Nuage de Magellan, Naine du Sagittaire, NGC 6822, IC 10, Leo I). Chaque sprite est généré séparément (`generateRealGalaxySprite()` / `generateMilkyWay()` dans `generate_simulated_textures.mjs`), dimensionné sur SA PROPRE taille (résolution relative identique pour toutes, quelle que soit leur distance réelle), avec un halo doux qui s'étend au-delà du nuage d'étoiles net pour amorcer une transition avec le layer de densité au-dessus (§4.6). La Voie lactée est dessinée EN PREMIER (dessous) : son halo, même réduit, ne doit jamais pouvoir recouvrir visuellement une galaxie plus proche (la Naine du Sagittaire, à seulement 0,024 Mpc, est la plus proche des 8).

3. **`localgroup`** (`DensityLayer.tsx`, texture `density_localgroup.png`) : texture procédurale pour les ~90 galaxies de champ NON nommées du Groupe Local (halo dépendant de la distance, pas de sprite individuel) — cf. `generate_local_group_texture.py`.

4. **`l1b` → `l5`** (`DensityLayer.tsx`) : 10 layers procéduraux de densité (doublé depuis 5 initialement) : `l1b`, `l2`, `l2b`, `l3`, `l3b`, `l4`, `l4a`, `l4b`, `l5a`, `l5`. Les paliers "a"/"b" sont des paliers TECHNIQUES (pas de nouveaux layers scientifiques). Champ gaussien aléatoire (GRF) généré GRAND → PETIT (`l5`, le plus grand et le plus lisse, sert de racine ; chaque layer plus fin hérite de son plus proche ancêtre scientifique et y ajoute du détail passe-haut, poids 0,74/0,67) — cf. §4.3-4.4, principe **non modifié** malgré la tentation d'inverser ce sens (cf. §4.7). En plus de ce champ hérité, `l1b`/`l2`/`l2b` reçoivent un ANCRAGE ADDITIONNEL sur les positions réelles du catalogue du Groupe Local (98 galaxies), avec une intensité décroissante à mesure qu'on s'éloigne, volontairement arrêtée à `l2b` (~67 Mpc) — cf. §4.7.

**Fichiers de génération (dans `/scripts`)**
- `generate_layers.py` (Python) : génère les 10 textures procédurales de densité (résolution 1024, marge de génération ×1,5 — ×2,4 pour L5 spécifiquement, seul layer visible pile à son bord extrême) + l'ancrage du Groupe Local sur `l1b`/`l2`/`l2b` (fonction `apply_local_group_anchor`, cf. §4.7).
- `generate_simulated_textures.mjs` (Node) : génère la texture `milkyway` (disque + bulbe, via le vrai `GalaxyModel` distant) et les 9 sprites individuels de `RealGalaxiesLayer` (Voie lactée + 8 galaxies réelles, avec halo).
- `generate_local_group_texture.py` (Python) : texture `localgroup` (galaxies procédurales non nommées).
- `generate_local_group_catalog.py` (Python) : construit le catalogue JSON de 98 galaxies (8 réelles nommées, positions/tailles réelles + ~90 galaxies de champ procédurales, distance 1-10 Mpc, `isReal: false`) — SOURCE UNIQUE consommée à la fois par `RealGalaxiesLayer.tsx`, `generate_local_group_texture.py` et `generate_layers.py`.
- `local_group_style.py` (Python) : source unique des constantes de rendu des galaxies réelles pour le champ de densité (taille de halo, suppression de bruit local...) — ne jamais redéfinir ailleurs.

**Processus de développement/validation pour tout travail génératif ou visuel** : cf. §13 — toujours valider par un calcul objectif hors-ligne (`scripts/dev/`) avant de présenter un résultat comme corrigé, jamais sur la seule base des courbes de paramètres.

**Points de vigilance connus — synchronisation manuelle requise**
- `app/public/glow-test.html` duplique manuellement la liste des layers de densité et leurs marges (pas de build partagé). Toute évolution côté production (`DensityLayer.tsx`) doit être répercutée à la main, sinon désynchronisation silencieuse (déjà arrivé une fois).
- `app/public/l1b-anchor-test.html` est un outil de calibration VISUELLE (aperçu approximatif, bruit de démonstration plutôt que le vrai champ BBKS) — les valeurs qu'il affiche sont un point de départ à reporter et affiner dans `generate_layers.py`, pas une garantie de rendu pixel-identique.
- `generateRealGalaxySprite()`/`generateMilkyWay()` (JS, `generate_simulated_textures.mjs`) et `RealGalaxiesLayer.tsx` partagent des constantes (`SPRITE_MARGIN`, le rayon de la Voie lactée) qui doivent rester synchronisées manuellement entre les deux fichiers — commentées explicitement à chaque occurrence.
- `field_to_log_density()` (dans `generate_layers.py`) applique un `exp()` avant le calcul de densité — toute valeur ajoutée en amont (ex. un ancrage) y est donc amplifiée de façon EXPONENTIELLE, pas linéaire. Une amplitude qui semble modeste dans le champ brut peut dominer complètement l'export après ce passage ; à l'inverse, un flou (`gaussian_filter`) appliqué avant ce transform peut détruire une texture fine de façon disproportionnée. Toujours vérifier le résultat exporté (histogramme, écart-type, comparaison visuelle), pas seulement les paramètres d'entrée.

**Chantiers en attente, déjà cadrés (cf. §11, qui remplace/complète §9)**
L'axe du temps (a(t)) n'est pas encore implémenté en production : actuellement la carte est en coordonnées comobiles fixes (rien ne bouge avec le temps, seule la luminosité change). La conception complète — compression spatiale, dissolution des structures par époque de formation propre à chaque échelle, règle de composition "screen" (jamais de flou ni de calque couleur), moteur N-corps pour l'accrétion des galaxies, embrasement par décalage avant transformation — est documentée en détail au §11 (matrice zoom × temps), avec plusieurs prototypes déjà réalisés et listés en §11.9. **Depuis le 13 juillet, la matrice de paramètres est formalisée et validée** : `app/public/data/spacetime_matrix.json` (source de vérité) + `docs/matrice-parametres-zoom-temps.md` (documentation/flux d'ajustement) + 114 frames temporelles cuites + prototype 2 curseurs `spacetime-matrix-test.html` — cf. §11.6/§11.9. Un seul changement est aussi prévu pour le rendu à `a=1` (aujourd'hui) par rapport à la production actuelle : un léger ancrage de densité permanent sur les 98 galaxies du Groupe Local, sur les layers à sprites (§11.4.d), pour une moyenne de couleur cohérente avec les layers de densité au-dessus. Reste à intégrer en production.

---

## 1. Vision du projet

Application web dynamique représentant l'univers observable en coupe 2D ("vu du dessus"), pilotée par deux axes de navigation indépendants :

- **Axe de zoom (échelle spatiale)** : de la Voie lactée et son environnement proche jusqu'à ~95 milliards d'années-lumière de diamètre (taille actuelle de l'univers observable).
- **Axe temporel** : du découplage matière-rayonnement (~380 000 ans après le Big Bang) jusqu'à aujourd'hui (13,8 milliards d'années).

L'application doit permettre de visualiser simultanément :
1. La structure hiérarchique de la matière (galaxies → amas → filaments → toile cosmique → homogénéité).
2. L'expansion physique de l'espace (dilution de la densité + croissance de l'horizon observable).

Le choix de la 2D est délibéré : il permet d'observer clairement les irrégularités de densité et les grandes structures sans l'occlusion propre à la 3D.

---

## 2. Système de coordonnées — principe fondamental

**Décision d'architecture centrale : la carte est un référentiel en coordonnées comobiles fixes.**

- La grille de la carte (95 milliards d'années-lumière de côté à son échelle maximale) ne bouge jamais, quelle que soit la position du curseur temporel.
- Ce qui varie avec le temps, c'est :
  - le **facteur d'échelle a(t)**, qui convertit une distance comobile en distance physique réelle à cette époque,
  - le **rayon de l'horizon observable** (particle horizon), qui croît avec le temps sur cette grille fixe,
  - la **densité de matière affichée**, qui se dilue avec l'expansion.

Ce choix résout élégamment trois problèmes soulevés pendant la phase de cadrage :
1. Pas besoin de reprojeter/redessiner la grille à chaque pas de temps — seule une couche d'échelle et un cercle de rayon variable changent.
2. La confusion initiale entre "distance parcourue par la lumière" et "distance réelle actuelle" ne se pose plus : on travaille nativement en comobile.
3. La question de l'héritage entre layers de zoom devient un problème de filtrage sur un champ figé, pas de régénération.

### 2.1 Rappel des trois notions de distance (pour la documentation interne)

| Distance | Définition | Usage dans l'app |
|---|---|---|
| Comobile | Distance fixe dans le référentiel en expansion, ne change jamais pour deux points sans mouvement propre | Système de coordonnées de la carte |
| Propre (physique) | Distance réelle à un instant t = distance comobile × a(t) | Utilisée pour convertir densité, tailles physiques affichées en légende |
| Parcourue par la lumière (lookback) | c × temps de trajet du photon | Utile uniquement pour les explications pédagogiques, pas pour le rendu |

---

## 3. Modèle cosmologique (axe temporel)

### 3.1 Paramètres retenus (Planck 2018, base-ΛCDM)

```
H0  = 67.4 km/s/Mpc      (constante de Hubble)
Ωm  = 0.315              (densité de matière, baryonique + noire)
ΩΛ  = 0.685              (densité d'énergie noire)
Ωr  = 9.24e-5            (densité de radiation — négligeable après recombinaison)
Âge de l'univers : 13.797 Ga (calculé, cohérent avec la valeur Planck)
```

### 3.2 Facteur d'échelle a(t)

Pour tout t postérieur à la recombinaison (domaine couvert par le curseur), la radiation est négligeable et la solution fermée matière + énergie noire s'applique :

```
a(t) = (Ωm/ΩΛ)^(1/3) · [ sinh( (3/2)·√ΩΛ·H0·t ) ]^(2/3)
```

avec convention a(aujourd'hui) = 1. Cette formule unique couvre tout l'intervalle du curseur temporel (découplage → aujourd'hui), avec une légère approximation près du découplage (radiation non totalement nulle à z~1100, écart négligeable pour l'usage visuel).

### 3.3 Facteur de dilution de densité

```
densité_affichée(t) = densité_référence_aujourd'hui × [1 / a(t)³]
```

C'est ce facteur scalaire, appliqué uniformément à tous les layers actifs, qui traduit "l'élastique qui se resserre" quand on remonte dans le temps.

### 3.4 Rayon de l'horizon observable (comobile)

Calculé par intégration complète de l'équation de Friedmann (radiation + matière + énergie noire) :

```
χ(t) = ∫₀ᵗ c·dt' / a(t')
```

Valeurs de référence à intégrer dans le moteur de rendu (pré-calculées, interpolées à l'exécution) :

| Époque | Âge | a(t) | Rayon comobile horizon | Facteur dilution 1/a³ |
|---|---|---|---|---|
| Recombinaison (z≈1100) | 0,00038 Ga | 0,00091 | 0,28 Gpc (~0,9 Gal) | ~1,3 × 10⁹ |
| z=10 | 0,47 Ga | 0,091 | 4,51 Gpc (~14,7 Gal) | ~1 288 |
| z=1 | 5,84 Ga | 0,50 | 10,74 Gpc (~35 Gal) | ~8,3 |
| Équivalence matière/ΛCDM (z≈0,3) | 10,25 Ga | 0,77 | 12,91 Gpc (~42 Gal) | ~2,5 |
| Aujourd'hui | 13,80 Ga | 1,0 | 14,14 Gpc (~46,1 Gal) | 1 |

**Recommandation d'implémentation** : générer une table de ~200-500 points (t, a, χ) par intégration numérique offline (script Python), puis interpoler (spline) côté client — évite de faire tourner un solveur d'ODE dans le navigateur.

### 3.5 Rendu visuel de l'expansion

Deux effets superposés, tous deux pilotés par a(t) :

1. **Grille de fond visible** : lignes de repère qui se resserrent/étirent avec a(t), rendant l'expansion perceptible à l'œil (effet "élastique").
2. **Dilution de la densité de matière** : facteur 1/a³ appliqué au champ de densité (voir §4).
3. **Cercle de l'horizon observable** : rayon = χ(t) sur la grille comobile fixe, croissant du centre vers les bords de la carte à mesure que le temps avance.

### 3.6 Les trois sphères cosmologiques

Au-delà de l'horizon des particules (limite de ce qu'on peut voir, déjà traité en §3.4), deux autres sphères, distinctes et souvent confondues, sont à représenter :

**Sphère de Hubble** — distance à laquelle la vitesse de récession (due à l'expansion) égale c :
```
R_Hubble(t) = c / H(t)
```
Ce n'est pas un horizon : on peut voir au-delà. Son rayon comobile croît puis **décroît** une fois l'expansion accélérée (retournement vers z≈0,63, t≈7,7 Ga).

**Horizon des événements** — distance comobile maximale au-delà de laquelle un photon émis aujourd'hui ne nous atteindra jamais :
```
D_event(t) = a(t) · ∫ₜ^∞ c dt' / a(t')
```
Son rayon comobile décroît de façon monotone ; sa distance propre converge vers une valeur finie asymptotique (~17,5 Gal).

**Table de valeurs (paramètres Planck 2018), rayons comobiles — à utiliser directement pour le rayon des cercles sur la carte** :

| Époque | a(t) | z | Âge (Ga) | R_Hubble comobile (Mpc) | Horizon événements comobile (Mpc) | Horizon particules comobile (Mpc, réf. §3.4) |
|---|---|---|---|---|---|---|
| Recombinaison | 0,00091 | 1100 | 0,0004 | 208 | 18 974 | 278 |
| z=10 | 0,091 | 10 | 0,47 | 2 384 | 14 737 | 4 515 |
| z=3 | 0,25 | 3 | 2,14 | 3 895 | 11 613 | 7 639 |
| z=1 | 0,50 | 1 | 5,84 | 4 968 | 8 509 | 10 743 |
| **Retournement Hubble** | 0,613 | 0,63 | 7,69 | **5 064 (maximum)** | 7 485 | 11 767 |
| z=0,5 | 0,667 | 0,5 | 8,58 | 5 046 | 7 059 | 12 193 |
| **Aujourd'hui** | 1,0 | 0 | 13,79 | 4 448 | 5 108 | 14 144 |
| Futur (a=1,5) | 1,5 | -0,33 | 20,12 | 3 361 | 3 520 | 15 732 |
| Futur (a=2) | 2,0 | -0,5 | 24,95 | 2 613 | 2 663 | 16 589 |
| Futur (a=5) | 5,0 | -0,8 | 40,86 | 1 073 | 1 069 | 18 183 |

**Observation clé pour le rendu** : sur la grille comobile fixe, l'horizon des particules est le seul des trois cercles qui grandit sans cesse. La sphère de Hubble grandit puis se rétracte vers le centre après le retournement (il y a ~6 Ga). L'horizon des événements se rétracte vers le centre depuis le début de la simulation. Dans le futur lointain, Hubble et horizon des événements convergent presque vers la même taille (ils tendent asymptotiquement vers la même valeur en régime de Sitter pur).

**Ordre observé aujourd'hui** : Hubble (14,5 Gal propre) < horizon des événements (16,7 Gal propre) < horizon des particules (46,1 Gal propre). Cet ordre a varié dans le passé — utile comme repère pédagogique dans l'UI ("à cette époque, quelle sphère est la plus grande ?").

### 3.7 Contrôles UI dédiés aux trois sphères

- Trois cercles superposables indépendamment activables (cases à cocher / boutons toggle), chacun avec sa propre couleur et légende.
- Étiquette dynamique affichant le rayon propre actuel de chaque sphère active, mise à jour en continu avec le curseur temporel.
- Bouton « isoler » par sphère : ajuste automatiquement le zoom pour cadrer précisément la sphère sélectionnée à l'instant courant (voir §8, animations guidées).

---

## 4. Système de layers spatiaux (axe de zoom)

### 4.1 Découpage en 5 layers conceptuels, avec plages de validité en échelle comobile

| # | Layer | Échelle (Mpc comobile) | Échelle (années-lumière) | Nature de la structure |
|---|---|---|---|---|
| 1 | Local | 0 – 3 | 0 – 10 millions | Voie lactée, Groupe Local — positions réelles connues, pas de génération statistique |
| 2 | Amas de galaxies | 3 – 30 | 10 – 100 millions | Amas, fonction de corrélation croissante |
| 3 | Toile cosmique | 30 – 150 | 100 – 500 millions | Filaments, murs, vides ; distance caractéristique inter-superamas ~120-140 h⁻¹ Mpc |
| 4 | Transition vers l'homogénéité | 150 – 300 | 500 Ma – 1 Ga | Zone de fondu entre structure et uniformité ("End of Greatness" débattu entre 100 et 300 Mpc) |
| 5 | Univers homogène | 300 – 14 400 | 1 Ga – 47 Ga (rayon) | Densité uniforme extrapolée, conforme au principe cosmologique |

Ce découpage en 5 est conceptuel/scientifique. L'implémentation réelle compte davantage de layers techniques (cf. §0 et §4.6-4.7) : le layer 1 "Local" est en réalité 3 composants de rendu distincts (`milkyway`, `RealGalaxiesLayer`, `localgroup`), et les layers 2 à 5 comptent 10 paliers techniques (`l1b` → `l5`) plutôt que 4, pour une résolution apparente plus régulière au fondu.

### 4.2 Mécanisme de transition entre layers (zoom)

- Chaque layer/composant est un canvas indépendant, avec sa propre opacité pilotée par une fonction de poids partagée (`layerWeights.ts`) — un seul calcul, réutilisé par tous les composants de rendu, pour garantir qu'aucun ne se désynchronise des autres.
- Au passage d'une plage de validité à l'autre, un **fondu d'opacité** (crossfade) est appliqué entre le layer sortant et le layer entrant, sur une zone tampon.
- Le layer 1 (local) n'est pas généré comme un champ statistique — c'est une combinaison de positions réelles connues (Voie lactée + 8 galaxies nommées, cf. §4.6) et d'une texture procédurale légère pour le reste du Groupe Local (`localgroup`).

### 4.3 Génération de la matière — méthode retenue

**Champ gaussien aléatoire (GRF) contraint par le spectre de puissance cosmologique P(k), puis transformation log-normale.**

Pipeline :
1. Calcul de P(k) via une formule de transfert analytique (Eisenstein & Hu 1998, sans nécessiter de solveur de Boltzmann complet).
2. Tirage d'un champ gaussien 2D en espace de Fourier : amplitudes fixées par √P(k), phases aléatoires (mais **fixées une fois pour toutes** — voir §4.4).
3. Transformation inverse de Fourier (FFT2D) → champ réel.
4. Transformation log-normale pour garantir des densités positives et un bon accord avec les statistiques observées (fonction de corrélation, pic BAO ~150 Mpc) :

```
δ_lognormal(x) = exp( δ_gaussien(x) − σ²/2 ) − 1
```

**Point d'implémentation important** (cf. §0, point de vigilance) : cette transformation log-normale implique un `exp()` — toute contribution ajoutée au champ gaussien AVANT cette étape (par exemple l'ancrage du Groupe Local, §4.7) y est amplifiée exponentiellement, pas linéairement. Une amplitude modeste dans le champ brut peut dominer complètement l'export final.

### 4.4 Héritage entre layers (exigence initiale du projet)

**Principe : un seul champ gaussien de base par région, décliné en plusieurs résolutions par filtrage passe-bas successif — pas un champ indépendant par layer.**

- Layer 5 (homogène) → Layer 4 → Layer 3 → Layer 2 : chaque niveau ajoute des fréquences plus hautes (détails plus fins) au-dessus de la structure déjà présente au niveau parent, en réutilisant les mêmes phases aléatoires.
- Techniquement : filtres gaussiens/passe-bas à des coupures d'échelle croissantes (analogue aux filtres à 4, 2, 1 h⁻¹ Mpc utilisés en recherche pour visualiser la toile cosmique à plusieurs résolutions), soit encore une approche "multi-octaves" calée sur P(k) plutôt que sur un bruit arbitraire.
- Conséquence pratique : quand on zoome sur une région, le layer plus détaillé n'invente pas une nouvelle distribution — il **précise** celle déjà visible au zoom précédent.
- **Ce sens (grand → petit) est un principe physique, pas seulement un choix d'implémentation, et n'a pas vocation à être inversé** — cf. §4.7 pour la discussion complète et ce qui a été fait à la place pour intégrer les données réelles du Groupe Local.

### 4.5 Interaction zoom × temps

Le facteur de dilution 1/a³ (§3.3) s'applique **après** la génération spatiale du champ de densité — il est indépendant de l'échelle affichée. Le champ de densité de base est généré à z=0 (aujourd'hui) ; on le dilue ensuite dans le temps.

### 4.6 Rendu des galaxies réelles connues (Voie lactée + Groupe Local proche)

**Contexte** : contrairement aux layers `l1b`→`l5` (structure statistique, générée), les positions de la Voie lactée et des 8 galaxies réelles nommées du Groupe Local sont CONNUES (catalogue `generate_local_group_catalog.py`) et doivent rester identifiables visuellement (formes distinctes, pas de simple point) sur toute la plage de zoom où elles sont physiquement pertinentes.

**Méthode retenue : un sprite pré-cuit dédié par galaxie, composé au runtime.**

- Chaque galaxie (Voie lactée comprise) a sa PROPRE texture (256-320 px), générée hors-ligne à une résolution dimensionnée sur SA PROPRE taille angulaire — donc la même finesse relative pour toutes, quelle que soit leur distance réelle. Une texture partagée pour l'ensemble du Groupe Local a été essayée puis écartée : à l'échelle de 2,4-3,6 Mpc, chaque galaxie n'occupait que quelques pixels et perdait toute structure reconnaissable (bras spiraux, barre...).
- Chaque sprite combine un nuage d'étoiles net (positions générées selon la morphologie propre à la galaxie — spirale, barrée, irrégulière à aile tidale, elliptique étirée) ET un halo doux qui s'étend nettement au-delà de ce nuage, en s'estompant progressivement jusqu'au bord du sprite. Ce halo sert de transition visuelle vers le layer de densité procédural juste au-dessus (`l1b`) — sans lui, la rupture entre "une galaxie physique nette" et "un champ de densité flou" était trop brutale.
- Composés au runtime par `RealGalaxiesLayer.tsx` : position/taille recalculées à chaque zoom (`distanceMpc`/`angleDeg`/`radiusMpc` du catalogue → coordonnées écran), un `drawImage` par galaxie visible. Reste un rendu "en direct" par nécessité, mais léger (quelques appels, jamais un rendu étoile par étoile).
- La Voie lactée est un sprite parmi les autres (distance 0), avec son propre halo — délibérément plus resserré que celui des 8 galaxies réelles : la galaxie réelle la plus proche (Naine du Sagittaire, 0,024 Mpc) est trop proche pour tolérer un halo aussi large que les autres sans les recouvrir visuellement. Dessinée en premier (dessous) par précaution supplémentaire.
- Visible sur toute la plage combinée `milkyway` + `localgroup` (somme des deux poids de fondu), sauf la Voie lactée elle-même qui n'utilise que le poids `localgroup` seul (pour ne pas se superposer à la texture `milkyway`, plus détaillée, pendant le zoom rapproché).

### 4.7 Ancrage du Groupe Local sur les layers de densité proches — portée et limite volontaire

**Question posée en cours de projet** : puisque les positions réelles du Groupe Local sont connues (§4.6) et que `l1b` (le layer de densité le plus proche) est généré statistiquement, ne devrait-on pas faire remonter cette connaissance réelle VERS les layers plus grands, plutôt que de laisser `l1b` ignorer superbement les 98 galaxies visibles juste en dessous ?

**Ce qui n'a PAS été fait, et pourquoi** : inverser le sens de génération du champ aléatoire lui-même (faire de `l1b` la racine et remonter vers `l5`) contredirait le principe cosmologique (§4.1, ligne 5) : à grande échelle (300+ Mpc), l'univers est statistiquement homogène et rien ne distingue notre position — construire les grandes échelles à partir d'une région locale connue introduirait un artefact scientifiquement faux (un point spécial fixe au centre de la carte, visible même là où aucun point de l'univers n'est censé se distinguer). Le sens grand → petit du champ aléatoire (§4.4) reste donc inchangé.

**Ce qui a été fait à la place** : une contrainte LOCALE, additionnelle et bornée, superposée au champ statistique existant — sans changer son sens de génération.

- `l1b` (8,49 Mpc) : ancrage complet sur les 98 galaxies du catalogue (8 réelles + ~90 procédurales de champ, cf. `generate_local_group_catalog.py`). Fonction `apply_local_group_anchor()` dans `generate_layers.py` : chaque position reçoit un halo doux + un pic, dimensionnés pour rester visibles (jamais sub-pixel, quelle que soit la résolution du layer) et pour se fondre dans la texture plutôt que de créer des ronds nets isolés (calibré visuellement via `l1b-anchor-test.html`, §0).
- `l2` (30 Mpc) et `l2b` (67,08 Mpc) : la même contrainte, mais en TRACE fortement atténuée (paramètre `strength`, 0,4 puis 0,15) — juste assez pour que les positions ne disparaissent pas net à chaque frontière de zoom, pas pour les rendre identifiables individuellement.
- **Arrêt volontaire à `l2b`** : au-delà (`l3`, 150 Mpc, et tous les layers suivants), aucun ancrage — le Groupe Local redevient statistiquement invisible, comme n'importe quelle autre région à cette échelle. C'est le comportement scientifiquement correct, pas une limitation technique à lever plus tard.

**Paramètres de `apply_local_group_anchor()`** (cf. docstring de la fonction pour le détail) : `strength` (intensité globale de l'ancrage), `global_suppression` (atténuation du bruit ambiant existant, pour laisser ressortir les positions ancrées), `size_multiplier` (taille des pics, en multiple de la résolution du layer), `bump_amplitude_factor` (luminosité des pics), `extra_blur_px` (flou d'ensemble — à utiliser avec prudence, cf. §0 sur le piège du transform `exp()`), `diffuse` (désactive le mécanisme "pic garanti dominant + suppression locale du bruit" au profit d'un simple ajout par-dessus le champ existant, pour un rendu moins "rond et net"), `real_only` (limite le traitement complet aux 8 galaxies nommées si `True` ; `False` sur `l1b`/`l2`/`l2b` pour couvrir les 98).

### 4.8 Ancrage résiduel sur `localgroup` — calibré le 10 juillet, pas encore implémenté

**Problème mesuré** (pas juste supposé) : `density_localgroup.png` a une moyenne de 0,23/255 (99,7% des pixels quasi noirs), contre 126,24 pour `density_l1b.png` — le layer immédiatement adjacent en zoomant. Cette rupture de près de 550× est exactement le défaut décrit en §11.1 point 3 et §11.4.d, mesurable dès aujourd'hui (`a=1`), pas seulement au moment d'une future convergence temporelle.

**Correctif calibré par le calcul** (`scripts/dev/` — sweep d'amplitude, pas une valeur devinée) :

- **Fichier concerné : uniquement `generate_local_group_texture.py`.** Ni `generate_simulated_textures.mjs` (sprites + `milkyway`), ni `RealGalaxiesLayer.tsx` n'ont besoin d'être modifiés — `localgroup` est déjà le layer responsable de la texture ambiante à cette échelle de zoom (visible dans le même composite que `RealGalaxiesLayer`, cf. §4.6), c'est donc lui qui doit porter cette correction.
- **Technique** : même génération FFT à spectre de puissance que `l1b`/`l2` (`generate_raw_field`, §4.3), sur le même box physique déjà utilisé par ce script (`2 × MAX_MPC × MARGIN_FACTOR = 7,2 Mpc`), variance normalisée à 1.
- **Intégration** : ce champ de fond est ADDITIONNÉ au champ existant (halos + cœurs des 98 galaxies, déjà calculé par `build_field()`) — pas un nouveau layer séparé, pas de nouvelle entrée dans `layerWeights.ts` :
  ```
  champ_final = champ_existant(98 galaxies) + amplitude_fond × champ_FFT_normalisé(seed=31415)
  norm = clip(champ_final / VMAX_REFERENCE, 0, 1)      # VMAX_REFERENCE=4.074, déjà utilisé, inchangé
  ```
- **Amplitude retenue : `amplitude_fond = 0,35`.** Calibrée pour amener la moyenne exportée de 0,23 à **8,95/255** — une amélioration nette (×39) sans se rapprocher de la moyenne de `l1b` (126) : `localgroup` doit rester visiblement plus sombre/épars que `l1b`, cohérent avec une structure moins développée à cette échelle plus proche. Vérifié : saturation négligeable (0,02% de pixels `>240`, comparable aux cœurs de galaxies déjà brillants avant ce correctif).

Ce correctif est la SEULE différence volontaire entre l'état de production actuel (`a=1`) et la matrice complète à générer (cf. §11.7, non-régression) — tout le reste du rendu à `a=1` doit rester strictement identique à l'existant.

---

## 5. Architecture technique (proposition initiale)

### 5.1 Séparation des responsabilités

| Composant | Rôle | Calcul |
|---|---|---|
| Générateur de champs (offline) | Pré-calcule les champs gaussiens/log-normaux pour chaque layer, à une résolution fixe, sérialisés en textures | Script Python/Node, exécuté une fois, pas en temps réel |
| Table cosmologique (offline) | Pré-calcule a(t), χ(t) sur ~200-500 points | Script Python (scipy.integrate) |
| Moteur de rendu (client) | Interpole a(t)/χ(t), applique la dilution de densité, gère le fondu entre layers, dessine la grille et le cercle d'horizon | WebGL/Canvas (ou React + shaders) |
| Contrôles UI | Deux curseurs (zoom, temps) synchronisés avec le moteur de rendu | React |

### 5.2 Format des données précalculées

- Champs de densité : textures (PNG 16 bits ou format flottant type EXR/raw), une par layer, résolution à définir selon performance cible.
- Table cosmologique : JSON `{ t, a, chi_comobile }` avec interpolation spline côté client.

### 5.3 Pourquoi précalculer plutôt que générer en temps réel

- Les FFT2D à haute résolution et l'intégration de Friedmann sont coûteuses ; elles n'ont pas besoin d'être recalculées à chaque frame.
- Seuls les paramètres dérivés du temps (opacités, facteur de dilution, rayon du cercle) doivent être recalculés en continu — ce sont des opérations légères (interpolation, multiplication scalaire).

---

## 6. Points ouverts / décisions à prendre en phase de prototypage

1. **Résolution des textures de densité** par layer (compromis qualité visuelle / poids de téléchargement).
2. **Nombre exact de points de la zone tampon de transition** entre layers (largeur du fondu).
3. **Choix du moteur de rendu** : Canvas 2D (plus simple) vs WebGL/shaders (plus performant pour les transitions temps réel et les effets de grille).
4. **Niveau de détail du Layer 1 (local)** : faut-il un vrai catalogue de positions du Groupe Local, ou une représentation stylisée ?
5. **Légendes/échelles affichées** : afficher la distance comobile, la distance propre actuelle, ou les deux simultanément à l'écran ?

---

## 7. Représentation du déplacement de la lumière et séquences d'animation

Objectif : rendre perceptibles, par le mouvement, les trois sphères et la distinction entre "vitesse de la lumière" et "vitesse d'éloignement dû à l'expansion" — une distinction qui reste abstraite tant qu'elle n'est montrée qu'à travers des formules ou des cercles statiques.

### 7.1 Traceur de rayon lumineux (cône de lumière passé)

- L'utilisateur clique un point de la carte (une galaxie, un emplacement quelconque) à une époque donnée.
- Le rayon lumineux émis vers nous à ce moment est tracé comme un point qui se déplace vers le centre, avec le temps qui avance sur le curseur.
- Le déplacement du photon suit `ds = c·dt / a(t)` en coordonnées comobiles : le photon avance plus vite en distance comobile quand a(t) est petit (univers jeune), puis ralentit en comobile à mesure que a(t) grandit.
- Effet pédagogique recherché : montrer que le trajet du photon vers nous n'est pas une ligne droite à vitesse comobile constante — il illustre concrètement l'intégrale qui définit l'horizon des particules (§3.4).
- Variante : proposer un point "aux limites de l'horizon des particules actuel" pré-sélectionné, dont le rayon retrace exactement 13,8 milliards d'années de trajet jusqu'à nous, timé sur le curseur.

### 7.2 Traceur de cône de lumière futur (horizon des événements)

- Même principe que 8.1 mais projeté vers l'avenir : on choisit un point aujourd'hui et on anime la propagation d'un photon émis maintenant vers l'extérieur.
- Si le point choisi est en-deçà de l'horizon des événements actuel, le photon continue de s'éloigner en distance comobile indéfiniment (jamais de convergence) — visuellement, on voit le point lumineux ralentir sa progression comobile sans jamais s'arrêter tout à fait, illustrant que "s'éloigner indéfiniment sans jamais atteindre une limite" correspond à "être dans notre cône de causalité futur".
- Si le point choisi est au-delà, le photon **n'avance plus du tout en coordonnées comobiles au-delà d'un certain point** — utile pour matérialiser concrètement ce que signifie "cette région ne recevra jamais notre lumière".

### 7.3 Galaxie traceur franchissant les sphères

- Placer un marqueur fixe en coordonnées comobiles (une galaxie choisie par l'utilisateur ou une galaxie repère prédéfinie, par exemple à 5 Gpc comobile).
- En faisant défiler le curseur temporel, le marqueur change d'état visuel selon sa position relative aux trois sphères à cet instant (à l'intérieur / à l'extérieur de chacune), par exemple via un code couleur ou une icône qui change.
- Effet recherché : rendre concret le fait qu'une même galaxie peut être visible mais en récession superluminale (hors sphère de Hubble, dans horizon des particules), ou destinée à ne jamais nous envoyer de nouvelle lumière (hors horizon des événements).
- Un effet de "décalage vers le rouge croissant puis quasi-figement" (analogie avec la chute dans un trou noir) peut accompagner le franchissement de l'horizon des événements par un objet qui s'en approche.

### 7.4 Time-lapse automatique (lecture continue)

- Bouton "lecture" qui anime automatiquement le curseur temporel de la recombinaison à aujourd'hui (et au-delà, en mode prospectif, si souhaité).
- Vitesse réglable, avec pause automatique aux instants clés déjà identifiés dans les tables (retournement de la sphère de Hubble, équivalence matière/énergie noire, etc.).

### 7.5 Zoom guidé — "suivre une sphère"

- Bouton "isoler"/"suivre" par sphère (mentionné en §3.7) : ajuste automatiquement le niveau de zoom en continu pendant la lecture du time-lapse, pour garder la sphère choisie visible en permanence à une taille constante à l'écran.
- Particulièrement utile pour la sphère de Hubble (dont le comportement croissant-puis-décroissant est sinon difficile à suivre visuellement si le zoom reste fixe).

### 7.6 Visualisation explicite "vitesse de la lumière vs vitesse d'expansion"

- Superposer, à un point donné de la carte, un repère mobile représentant "ce qu'un photon aurait parcouru en un temps donné à vitesse comobile constante" à côté du repère réel (qui suit `ds = c dt/a(t)`).
- Permet de visualiser directement l'écart entre les deux, et donc pourquoi certaines régions sont en récession superluminale sans que rien ne dépasse localement la vitesse de la lumière.

### 7.7 Priorisation suggérée pour un premier prototype

1. Time-lapse automatique (8.4) — base indispensable, réutilise directement les tables déjà définies (§3.4, §3.6).
2. Galaxie(s) traceur(s) franchissant les sphères (8.3) — fort impact pédagogique, complexité modérée.
3. Traceur de cône de lumière passé (8.1) — cœur scientifique du projet, complexité plus élevée (nécessite le calcul d'intégrale par point cliqué).
4. Zoom guidé (8.5) et cône futur (8.2) — raffinements à ajouter une fois le socle validé.

---

## 9. Proposition retenue — distension spatiale réelle en fonction du temps

**Statut : validé en discussion, pas encore implémenté (en attente d'un correctif de netteté au moment de la rédaction).**

### 9.1 Le problème

Le système de coordonnées comobiles fixes (§2) était un choix délibéré : un point ne bouge jamais à l'écran, seule sa luminosité change avec le temps (dilution ×1/a³, §3.3). Ce choix reste valide pour l'objectif initial, mais une demande complémentaire est apparue : **voir l'espace se comprimer visuellement** en remontant vers le Big Bang, pas seulement s'assombrir/s'illuminer sur place. Autrement dit, passer d'un rendu "en distance comobile" à un rendu "en distance physique réelle" (proper distance), qui elle se contracte authentiquement avec a(t).

Précision importante actée en discussion : cet effet est **indépendant** de la question de la croissance des structures (formation hiérarchique bottom-up, §7 — non traitée ici, mise de côté pour l'instant). Il s'agit uniquement de la distension métrique de l'espace, pas de l'évolution du contraste des structures.

### 9.2 Principe d'implémentation

Un seul point de conversion centralisé est utilisé par tous les composants de rendu (grille, textures de densité, Voie lactée, Groupe Local, cercle d'horizon) :

```
pxPerMpc_actuel  = écran / (2 × halfWidthMpc)
pxPerMpc_nouveau = écran / (2 × halfWidthMpc / a(t))
```

En divisant le champ de vue comobile par `a(t)`, on affiche mécaniquement une zone comobile plus grande dans le même espace écran quand `a(t) < 1` (passé) — ce qui fait rétrécir visuellement tout ce qui est fixe en comobile vers le centre. À `a(t) = 1` (aujourd'hui), aucune distorsion : le rendu est identique à l'existant. La distorsion n'apparaît qu'en remontant le temps.

**Pourquoi une seule formule suffit** : parce que tous les composants (DensityLayer, MilkyWayLayer, LocalGroupLayer, la grille et le cercle d'horizon dans UniverseMap) dérivent déjà leur échelle px/Mpc d'un seul et même calcul. Modifier ce calcul centralement propage l'effet partout sans toucher au reste du code de chaque composant.

### 9.3 Complémentarité avec la dilution de densité

Cet effet de compression spatiale et la dilution de densité (1/a³, déjà implémentée) sont **complémentaires, pas redondants** :
- La compression fait rétrécir l'espace visuellement (effet géométrique).
- La dilution fait que ce qui reste visible est plus dense/lumineux (effet de densité).

Combinés, ils donnent l'impression d'un univers qui se comprime ET s'embrase en remontant vers le Big Bang — cohérent avec l'intuition physique de départ du projet (cf. §1 et les tout premiers échanges de cadrage).

### 9.4 Points à vérifier à l'implémentation

- Vérifier que le cercle de l'horizon des particules (déjà dynamique, §3.4) reste cohérent visuellement avec cette compression additionnelle — les deux évoluent avec le temps mais via des mécanismes distincts (l'horizon via son propre calcul physique, ce nouvel effet via la conversion px/Mpc).
- Vérifier le comportement aux limites (a(t) très petit, proche de la recombinaison) : la formule doit rester stable numériquement.
- Décider si l'effet doit s'appliquer de façon identique à tous les layers ou si certains éléments (par ex. les étiquettes de texte, si réintroduites) doivent rester lisibles indépendamment de la compression.

---

## 11. Cohérence spatio-temporelle — matrice unifiée zoom × temps

**Statut : conception validée ET largement prototypée/calibrée par le calcul (8-10 juillet) — voir §11.9 pour l'état précis d'avancement. Pas encore intégrée dans les composants de production (`DensityLayer.tsx`, `RealGalaxiesLayer.tsx`), tout reste dans des prototypes autonomes `app/public/*-test.html` et des scripts `scripts/dev/`.**

### 11.1 Le problème que cette section résout

Le §9 traite la distension spatiale (le "dézoom" en remontant le temps) comme un effet géométrique isolé. En pratique, remonter le temps doit faire évoluer **cinq choses à la fois**, et ces cinq choses doivent rester cohérentes entre elles ET entre layers de zoom adjacents à tout instant t — sans quoi on obtient soit une rupture visuelle en changeant de zoom à temps fixé, soit une rupture en changeant le temps à zoom fixé :

1. **La position** (compression spatiale, §9/§11.4.e) — uniquement pertinente à partir de l'échelle où le flux de Hubble domine.
2. **La forme des structures** (nettes → filamenteuses → uniformes) — pas un flou géométrique, une réduction d'amplitude AVANT la transformation non linéaire qui crée les pics (§11.2).
3. **La luminosité moyenne du fond** — doit rester cohérente à tout instant t, quel que soit le layer regardé, y compris entre les layers à sprites et les layers de densité purs (§11.4.d).
4. **Le moment où chaque échelle commence à se dissoudre** — pas le même pour toutes : une galaxie et un amas de galaxies ne se sont pas formés à la même époque cosmique (§11.4.a).
5. **L'embrasement final** (convergence vers le blanc à la recombinaison) — un phénomène physiquement distinct des quatre précédents, qui ne doit s'activer que tout à la fin (§11.4.c).

Il n'existe que **deux types de contenu graphique** sur l'ensemble des layers (de zoom et de temps) : des **sprites de galaxies** (Voie lactée + 8 galaxies réelles nommées, visibles individuellement sur les layers de bas niveau de zoom) et un **layer de champ de densité** (plus ou moins condensé, filamenteux, ou uniforme), présent sur tous les layers à toute époque, y compris sous les sprites. Aucun troisième mécanisme n'est permis — toute variation visuelle doit venir des paramètres de génération de ces deux types de contenu, jamais d'un calque ou d'un effet de post-traitement générique ajouté à part.

### 11.2 Génération du champ de densité — pourquoi ni le flou ni le bruit interpolé ne sont utilisables

**Le flou géométrique a été essayé et rejeté** (sprites, 6-8 juillet) : un flou gaussien appliqué après coup donne des taches rondes lisses, jamais des filaments, et détruit la texture fine sans repasser par un état "toile cosmique" intermédiaire crédible.

**Un bruit interpolé en douceur (grille de valeurs + interpolation bilinéaire/smoothstep, type Perlin/value-noise) a ensuite été essayé comme alternative, et rejeté à son tour** (9-10 juillet) : même sans aucun flou explicite et même en régénérant le motif à une résolution source très élevée (testé jusqu'à 8192×8192), ce type de bruit reste un filtre passe-bas par construction — vérifié par le calcul (variance du laplacien, un indicateur direct de contenu haute fréquence) : elle s'effondre à quasi zéro dès qu'on tente de faire "grandir" ce bruit par un zoom, quelle que soit sa résolution source.

**Solution retenue** : un champ gaussien contraint par un spectre de puissance réaliste (FFT), exactement la méthode déjà utilisée en production pour `l1b`→`l5` (`generate_raw_field` dans `scripts/generate_layers.py`), combinée à deux techniques :

1. **Réduction d'amplitude avant la transformation non linéaire** (pas un flou sur le résultat) :
   ```
   field_to_log_density(champ) = log10( exp(champ − var(champ)/2) + 0.05 )
   ```
   Cette transformation exponentielle est ce qui **crée** les pics à partir d'un champ par ailleurs plat. En réduisant l'amplitude du champ gaussien source, le squelette filamenteux (déterminé par la PHASE du champ, inchangée) reste identique, mais les pics s'écrasent progressivement — un vrai état "toile cosmique diffuse" existe entre "aujourd'hui" et "uniforme". Vérifié numériquement sur `l2` (écart-type du champ normalisé : 0,200 à amplitude 1 → 0,004 à amplitude 0,02, moyenne stable ~0,4-0,5 tout du long).

2. **Croissance d'échelle des filaments dans le temps, sans perte de résolution réelle** : recadrer une portion de plus en plus petite d'un champ "maître" haute résolution (donne les grandes structures qui semblent grandir) **plus** un détail haute fréquence **fraîchement régénéré** à pleine résolution d'affichage à chaque palier temporel — jamais un recadrage seul (vérifié : sans détail frais régénéré, le contenu haute fréquence s'effondre au zoom, y compris avec un champ maître à très haute résolution).

En pratique : cuire hors-ligne une séquence de frames en niveaux de gris (comme tous les sprites du projet — couleur/palette au runtime), une par palier temporel pertinent, chargées et interpolées comme des sprites classiques. Ne jamais générer ce bruit en direct dans le navigateur avec une grille interpolée (implémenté et vérifié : `scripts/dev/generate_bg_filament_keyframes.py`).

### 11.3 Règle de composition — un seul opérateur, jamais de calque

Chaque source de contenu (sprites/points, champ de densité, embrasement, ancrages — §11.4.c/d) est calculée **indépendamment**, chacune passant par sa propre transformation non linéaire (`tone = 1 − exp(−champ_brut)`, ou l'équivalent `field_to_log_density` de production). Les sources sont ensuite combinées par un mélange type **"screen"** :

```
combiné = 1 − (1 − source_A) × (1 − source_B) × (1 − source_C) × ...
```

**Jamais** de flou de fusion appliqué après coup pour mélanger des éléments entre eux, **jamais** d'atténuation globale d'un layer vers une couleur/valeur unie pour le faire apparaître ou disparaître (mélange RGB linéaire type `couleur×(1−mix) + cible×mix`). Additionner plusieurs champs bruts dans un buffer commun avant une seule transformation reste correct uniquement quand il s'agit de la même nature de contenu (ex. plusieurs étoiles d'une même galaxie) — pas pour combiner des sources de nature différente (points vs champ de fond vs embrasement), qui doivent chacune garder leur propre netteté via le mélange "screen" ci-dessus.

Toute impression de "disparition" ou d'"uniformisation" doit venir des **paramètres de génération** du champ de densité qui convergent vers un état plat (§11.2), jamais d'un mélange de couleur après coup.

### 11.4 Les fonctions centrales (une seule définition, réutilisée partout)

**a) Époque de formation par échelle — `a_form(s)`**

Ancrée dans la recherche (8 juillet) : les galaxies sont des structures ANCIENNES (déjà à moitié assemblées vers z≈2,5-5), les amas de galaxies sont des structures JEUNES (se forment entre z≈0-1). En remontant le temps, les grandes échelles doivent donc se dissoudre BIEN AVANT les petites — et inversement, en descendant le temps (formation), les structures filamenteuses apparaissent d'abord aux petites échelles (galaxies), et seulement plus tard aux grandes échelles (amas/toile cosmique).

| Groupe de layers | Échelle (Mpc) | z de formation | a_form | Source |
|---|---|---|---|---|
| Sprites (Voie lactée + 8 galaxies réelles), `localgroup` | 0,01 – 2,4 | 2,5 – 5 | **≈ 0,20** | Demi-masse assemblée à ces z (recherche 8 juillet) |
| `l1b` | 8,49 | transition | **≈ 0,55** | Zone de retournement des amas |
| `l2` / `l2b` | 30 – 67 | 0 – 1 | **≈ 0,65 – 0,70** | Formation des amas (recherche 8 juillet) |
| `l3` → `l4b` | 150 – 2100 | ~0 (encore en formation) | **≈ 0,92 – 0,95** | Toile cosmique, encore jeune aujourd'hui |
| `l5a` / `l5` | 5531 – 14570 | — (toujours quasi homogène) | **≈ 1,0** | Aucune dissolution significative à faire |

**b) Amplitude de structure — `A(s, a)`**

Fonction en S (smoothstep), centrée sur `a_form(s)`, dans l'espace `log10(a)` :

```
demi_largeur(s) = max( −log10(a_form(s)), 0.05 )     [ADAPTATIVE par échelle — cf. contrainte ci-dessous]
x(s, a)  = log10(a) − log10(a_form(s))
t(s, a)  = clamp( (x + demi_largeur(s)) / (2 × demi_largeur(s)), 0, 1 )
A(s, a)  = 1                                          si a ≥ 1
A(s, a)  = t² × (3 − 2t)                              sinon   [smoothstep]
```

**Contrainte dure, vérifiée par le calcul** : `A(s, a=1) = 1` exactement et **continûment** (pas de saut juste avant `a=1`), pour **toute** échelle `s`. Une largeur de transition FIXE (essayée en premier, 0,6 dex) échoue cette contrainte pour les layers dont `a_form` est proche de 1 (`l2`/`l2b`/`l3`... donnaient `A(s,1) < 1`, ce qui aurait changé un rendu déjà calibré à "aujourd'hui"). La largeur **adaptative** ci-dessus (distance en dex entre `a_form(s)` et `a=1`) corrige ce défaut par construction.

**Correctif du 13 juillet (continuité, plancher actif)** : quand le PLANCHER de largeur (0,05 dex) est actif (`a_form > 10^−0,05 ≈ 0,891`, soit l3 → l5), la fenêtre centrée sur `log10(a_form)` déborde au-delà de `a=1` et `A` saute de 1 à ~0,5 juste sous `a=1` (mesuré : `A(l5, 1−ε)=0,4995`). La fenêtre est désormais recentrée pour se terminer TOUJOURS exactement à `a=1` : `centre = min(log10(a_form), −w)` — appliqué dans `spacetime-shared.js`, `scripts/dev/spacetime_pipeline.py` et `scripts/dev/validate_fullscene_render.py`. Sans effet pour les échelles à plancher inactif (galaxies, l1b, l2, l2b). Conséquence : les fenêtres de l3 → l5 coïncident sur `a ∈ [0,794, 1]` — cf. docs/matrice-parametres-zoom-temps.md §6.

**Utilisation de `A(s,a)` selon le type de layer :**
- Layers de densité (`l1b` → `l5`) : multiplie le champ gaussien source avant transformation non linéaire (§11.2).
- Sprites : pilote la croissance du halo par étoile et l'intensité de la texture filamenteuse. Paramètres validés (8 juillet, à conserver) : `pointSize=0,5`, `filamentAmount≈0,8` (cf. `scripts/generate_dissolution_sprites.mjs`). **Correctif du 10 juillet** : la croissance du rayon par étoile doit rester MODESTE (facteur `1 + progress×1.2`, pas `×6` ni `×8,5` comme testé initialement) — un rayon qui grandit fortement est lui-même un filtre passe-bas (une gaussienne plus large a moins de hautes fréquences) ; la dispersion spatiale visible doit venir de la VRAIE simulation N-corps (§11.5), pas d'un grossissement artificiel du rendu de chaque point. **Conservation du flux obligatoire** quand le rayon grandit : diviser l'amplitude par le CARRÉ du facteur d'élargissement (pas sa racine) — sans cette correction, le champ sature dès `a=1`, avant même toute dissolution, par simple chevauchement de milliers de particules (bug réel rencontré et corrigé, cf. `scripts/dev/validate_fullscene_render.py`).
- Ancrage forcé du Groupe Local sur `l1b`/`l2`/`l2b` (`apply_local_group_anchor`, §4.7) : le paramètre `strength` existant doit être multiplié par `A(s_local, a)` où `s_local` est l'échelle DES GALAXIES (≈0,03 Mpc, `a_form≈0,20`) — pas celle du layer qui accueille l'ancrage. L'ancrage reste net tant que les galaxies elles-mêmes sont formées, et se dissout avec elles.

**c) Embrasement (convergence vers le blanc à la recombinaison)**

**Corrigé le 10 juillet — la méthode ci-dessous remplace toute description antérieure de ce document mentionnant un calque de couleur mélangé (`universeGlowColor` en blend RGB linéaire) : cette ancienne méthode a été essayée puis rejetée, elle recrée exactement le défaut que §11.3 interdit.**

Pas de calque de couleur séparé. Un décalage (`embrasementOffset`) qui grandit UNIQUEMENT tout près de la recombinaison est ajouté aux champs bruts (sprites, fond) **avant** leur transformation non linéaire respective, puis combiné par le même mélange "screen" que le reste (§11.3) :

```
bgLateFade(a)      = 1 − A(0.03, min(a×6, 1))          [réutilise la courbe de dissolution des galaxies]
embrasementOffset(a) = bgLateFade(a)^5 × 18              [exposant et amplitude calibrés par le calcul]
whiteChannel(a)    = 1 − exp(−embrasementOffset(a))
combiné_final      = 1 − (1 − combiné) × (1 − whiteChannel)
```

Comme la valeur maximale de la palette de couleur (`colorForValue(1.0)`) correspond déjà exactement à la teinte de recombinaison visée (`#fff3d6`, la même que l'ancien `universeGlowColor` à `a→0`), saturer le ton vers 1 suffit — **pas besoin de mélanger vers une couleur cible explicite**, `#fff3d6` en est déjà le résultat naturel.

Calibré par le calcul (10 juillet) : reste nul jusqu'à `a≈0,1`, monte à `59%` vers `a=0,03`, atteint `100%` (blanc uniforme, exactement l'état physique visé) à l'approche de la recombinaison — progression continue, sans creux ni saut brutal (piège rencontré avec une première version basée sur une fenêtre étroite en `log(a)` près de `a_min`, qui créait un passage par le quasi-noir juste avant un saut).

**d) Ancrage de densité résiduel sur les layers à sprites — y compris à `a=1` (aujourd'hui)**

**Précisé le 10 juillet.** Les layers à sprites (`milkyway`, `RealGalaxiesLayer`) ont, en l'état actuel de production, un fond parfaitement noir autour des sprites — contrairement aux layers de densité qui ont une texture partout. Ça crée une rupture de luminosité moyenne avec le reste des échelles, visible dès `a=1` (pas seulement au moment de la convergence en remontant le temps).

**Correctif à intégrer, y compris dans le rendu de production à `a=1`** : ajouter un léger champ de densité, généré par le MÊME mécanisme que §11.2 (champ FFT, pas un bruit inventé séparément), **ancré sur les 98 galaxies du Groupe Local** (8 réelles nommées + 90 procédurales — même catalogue que `apply_local_group_anchor`, §4.7), avec une amplitude modeste et permanente (pas modulée à zéro à `a=1` — c'est justement là qu'elle sert). Objectif explicite : que la moyenne de couleur de `milkyway`/`RealGalaxiesLayer`/`localgroup` reste cohérente avec celle des layers de densité au-dessus, dès aujourd'hui, pas seulement en cas de convergence lointaine dans le temps.

**Valeurs concrètes calibrées par le calcul, fichier concerné, formule d'intégration : cf. §4.8** — ne pas redeviner ces paramètres, ils sont déjà mesurés (amplitude retenue 0,35, moyenne exportée cible 8,95/255, uniquement `generate_local_group_texture.py` à modifier).

Ce mécanisme est le même que l'ancrage par galaxie déjà validé pour la scène complète du Groupe Local en dissolution (§11.5, prototype `time-axis-fullscene-test.html`) : un renflement à la position réelle de chaque galaxie, mélangé par l'opérateur "screen" (§11.3) — simplement utilisé ici en permanence (amplitude non nulle même à `a=1`), plutôt que seulement comme effet de dissolution.

**e) Compression spatiale (rappel §9, bornée par la physique — §4.7)**

```
effectiveHalfWidthMpc(s, a) = halfWidthMpc / a(t)     si s ≳ 15-30 Mpc (flux de Hubble dominant)
effectiveHalfWidthMpc(s, a) = halfWidthMpc            si s ≲ 2 Mpc (Groupe Local, lié gravitationnellement)
```

Zone de transition entre les deux (≈2-15 Mpc, `l1b`) : traiter avec le même type de fondu en S que `A(s,a)`, pas une coupure nette.

**f) Rattachement du champ de fond aux coordonnées physiques — piège rencontré deux fois (10 juillet)**

Le champ de densité de fond DOIT être échantillonné dans le **même système de coordonnées physiques (Mpc)** que les sprites/galaxies qui l'accompagnent (mêmes `cx`/`cy`/`pxPerMpc`), pas par simple fraction de pixel écran indépendante du zoom choisi — sinon le curseur de zoom ne l'affecte pas du tout (bug réel n°1).

La fenêtre de mappage à l'AFFICHAGE doit rester le **champ de vue actuellement affiché** (`2×halfWidthMpc`, le demi-champ courant), CONSTANTE quelle que soit la frame temporelle utilisée — la croissance apparente des filaments est déjà entièrement contenue dans le contenu de chaque frame cuite (§11.2, technique de recadrage). Ne surtout pas appliquer un rétrécissement de fenêtre une deuxième fois au moment de l'affichage : ça confine le contenu visible à une zone centrale de plus en plus petite en remontant le temps au lieu de remplir le cadre — l'inverse de l'effet recherché (bug réel n°2, découvert après le premier correctif).

**Vérification obligatoire** (§13) : sur toute la grille temps × zoom, aucune zone du cadre affiché ne doit retomber sur une valeur neutre/par défaut (texture absente) — mesuré par calcul, pas estimé à l'œil.

### 11.5 Moteur N-corps pour l'accrétion/dissolution des galaxies

Pour chacun des 9 sprites (Voie lactée + 8 galaxies réelles), la dissolution/accrétion est simulée avec un vrai moteur N-corps — Barnes-Hut (quadtree, O(n log n)), intégration leapfrog, softening gravitationnel — pas une approximation procédurale. Implémenté et calibré : `scripts/simulate_dissolution.mjs` (généralisé depuis `scripts/simulate_milkyway_dissolution.mjs`), sprites cuits par `scripts/generate_dissolution_sprites.mjs`.

- **Position de départ** (aujourd'hui, `a=1`) : vraies positions d'étoiles (`GalaxyModel` pour la Voie lactée ; générateur de morphologie procédural — spiral/barré/irrégulier/elliptique selon la galaxie — pour les 8 autres, port de `generateNearbyGalaxyStars`).
- **Vitesse initiale** : radiale (dispersion, coefficient `0,0042×r`) + turbulente (aléatoire, casse la symétrie) + **tangentielle cohérente** (même sens pour toutes les particules d'une même galaxie, coefficient `0,0034×r`) — représente la conservation du moment angulaire : le nuage protogalactique s'est effondré en tourbillonnant pour créer la rotation actuelle. En remontant le temps, la rotation doit se "dérouler" visiblement, pas juste une explosion radiale.
- **Gravité mutuelle** laissée active pendant toute la dispersion (pas juste une expansion balistique) — donne des amas irréguliers persistants (cohérent avec la phénoménologie "galaxies grumeleuses" à grand redshift, JWST), pas une explosion uniforme. Constante d'accélération empirique calibrée par unités NORMALISÉES (rayon propre de chaque galaxie = 1) : `ACCEL_SCALE = 150000 / MW_R³` (dérivée dimensionnellement depuis la calibration absolue de la Voie lactée, `MW_R=52000` al — ne pas deviner cette constante empiriquement pour chaque nouvelle échelle, la dériver comme ceci évite un bug d'explosion numérique déjà rencontré).
- **Softening gravitationnel** : ≈ `0,0173` en unités normalisées (rayon propre = 1), pour éviter les forces infinies à courte distance.
- Combiner le résultat de cette simulation avec le layer de champ de densité de fond, ANCRÉ sur la position réelle de la galaxie (renflement d'amplitude croissante vers `a=1`, mélangé par l'opérateur "screen", §11.3/§11.4.d) — c'est ce qui fait que le fond se "rattache" visuellement à l'endroit où chaque galaxie s'est réellement formée, pas seulement les points de la simulation eux-mêmes.

### 11.6 Espace de paramètres à définir AVANT tout rendu

Avant de générer le moindre visuel, construire une matrice explicite (zoom × temps), et pour chaque cellule documenter :
- Présence ou non de sprites de galaxies individuels, et leur mode de génération (positions réelles `GalaxyModel` / morphologie procédurale / aucun sur ce layer).
- Niveau de couleur de fond moyen visé (calculable via `A(s,a)` et l'échelle de couleur, pas estimé à l'œil).
- Paramètres de génération du champ de fond : amplitude avant transformation non linéaire, échelle/recadrage du champ maître, seed.
- Niveau d'ancrage des galaxies (§11.4.d/§4.7) et son impact sur la génération du fond (amplitude, rayon d'influence).
- Taux de compression spatiale à appliquer (§11.4.e).
- Poids de fondu entre layers adjacents si plusieurs doivent se superposer à cette cellule précise.

Documenter cette matrice avant de produire le moindre visuel — c'est elle qui garantit la cohérence, pas une vérification a posteriori.

**Fait le 13 juillet** : matrice canonique versionnable dans `app/public/data/spacetime_matrix.json` (source de vérité éditable), documentée champ par champ dans **`docs/matrice-parametres-zoom-temps.md`** (provenance de chaque valeur, flux d'ajustement, table évaluée). Consommée telle quelle par `scripts/generate_spacetime_frames.py` (cuisson des 114 frames temporelles `st_*.png`), `scripts/dev/spacetime_pipeline.py` (pipeline headless partagé), `scripts/dev/validate_spacetime_matrix.py` (validation §13) et le prototype `app/public/spacetime-matrix-test.html`.

### 11.7 Non-régression

Le rendu à `a=1` (aujourd'hui) doit être strictement identique à la production actuelle déjà calibrée, à tout niveau de zoom, **à l'exception explicite de l'ajout du léger ancrage résiduel décrit en §11.4.d** (seule différence volontaire entre l'état de production actuel et la matrice complète à générer). Si un autre paramètre nouveau change ce rendu de référence, c'est un bug à corriger avant de continuer, pas un détail à ajuster plus tard.

### 11.8 Validation — obligatoire, cf. §13

Chaque mécanisme de cette section doit être validé par un script headless (§13) avant tout retour visuel demandé : saturation, contenu haute fréquence qui ne doit jamais tomber à zéro, continuité entre échantillons voisins, couverture complète du cadre à tout zoom/temps (§11.4.f), et `A(s,a=1)=1` exactement pour toute échelle (§11.4.b).

### 11.9 État d'avancement (prototypes déjà réalisés)

- `app/public/time-axis-test.html` : première version (compression + dissolution sur 3 échelles) — remplacée par les suivantes.
- `app/public/time-axis-milkyway-test.html` puis `time-axis-milkyway-nbody-test.html` : dissolution physique de la Voie lactée (séquence ELS 1962 inversée, puis vrai moteur N-corps).
- `app/public/time-axis-sprites-test.html` : généralisation aux 9 sprites.
- `app/public/time-axis-fullscene-test.html` : **le plus avancé** — les 9 sprites composés ensemble, fond FFT rattaché aux coordonnées physiques, ancrage par galaxie, embrasement par décalage (pas de calque couleur), mélange "screen" partout, animation Big Bang → aujourd'hui, validé par calcul à chaque itération.
- `app/public/spacetime-shared.js` : `aFormForScaleMpc`, `structureAmplitude` (= `A(s,a)`), `universeGlowColor` (⚠️ obsolète comme mécanisme d'embrasement principal depuis §11.4.c — la fonction reste valide comme définition de la teinte de référence, mais ne doit plus être appliquée en blend RGB direct).
- `scripts/simulate_dissolution.mjs` + `scripts/generate_dissolution_sprites.mjs` : simulation N-corps et cuisson des sprites (126 fichiers).
- `scripts/dev/generate_bg_filament_keyframes.py` : cuisson du champ de fond FFT (recadrage + détail frais).
- `scripts/dev/validate_fullscene_render.py` : script de validation headless de référence pour ce mécanisme — à consulter/étendre avant toute nouvelle itération (§13).

- **13 juillet — matrice complète zoom × temps** : `spacetime_matrix.json` (§11.6, source de vérité) + 114 frames temporelles cuites (`st_{layer}_k*.png`, 512², niveaux de gris) pour les 10 layers GRF ET `localgroup` (avec le correctif §4.8/§11.4.d intégré à `a=1` et un plancher de convergence vers le ton dissous partagé, cf. docs/matrice-parametres-zoom-temps.md §7) ; pipeline headless partagé `scripts/dev/spacetime_pipeline.py` ; validation complète `scripts/dev/validate_spacetime_matrix.py` (119 contrôles : A(s,1)=1 continu, non-régression a=1 frame par frame, saturation/continuité/HF des séquences, couverture §11.4.f, balayages denses avec preuve de lissité par division du pas) ; prototype **`app/public/spacetime-matrix-test.html`** (2 curseurs zoom × temps balayant TOUTE la carte, fond + sprites N-corps + embrasement) ; contrôle croisé Node exécutant le VRAI JS du prototype contre le pipeline Python (`scripts/dev/xcheck_dump_ref.py` + `xcheck_prototype.mjs`, écart max ~4e-6 — a détecté un vrai écart d'ordre d'application de l'embrasement le 13 juillet).

- **14 juillet — matrice v2** (`spacetime_matrix.json` version 2, détails dans docs/matrice-parametres-zoom-temps.md §§2, 9-11) : **axe de temps affiché en Gyr linéaire** (mapping `cosmology_table.json`, embrasement confiné à 0.31 % de la course — l'ancien curseur log(a) l'étalait sur 42 %) ; **effet d'expansion PAR ÉCHELLE** (nœuds `expansion.nodes` remplaçant la rampe lo=2/hi=15 qui violait §11.4.e et contractait le champ des galaxies liées ; `expansionStrengthFromNodes` dans `spacetime-shared.js`) ; **sprites N-corps CUITS** (les 126 frames `dissolution_sprites/` remplacent les splats runtime : morphologies restaurées, extinction `A_gal²` — les sprites se dissolvent dans le fond AVANT le fond, séquencement validé empiriquement — plancher de lisibilité sur le CŒUR `min_render_core_px × halfwidth_units` contre l'aliasing des naines) ; **layer `milkyway` réintégré** (sprite + fond localgroup) ; **nomenclature des cellules** `<lettre><chiffre>` (A..L = lignes de zoom, 0..10 = colonnes de temps linéaires en Gyr, ex. C7 = l1b à t≈9.65 Ga ; `cell_params()` dans le pipeline, montage étiqueté) ; validation portée à 157 contrôles (sections E expansion, F sprites, G axe Gyr, H nomenclature), contrôle croisé JS/Python étendu aux cellules à sprites (écarts ≤ 1e-7).

- **14 juillet — spécification v3 de la matrice** (validée par Marc, **non générée** — blocs `filamentarity`, `tone_mapping`, `field_evolution`, `real_galaxies.milkyway_hires` + liste `pending_generation` dans le JSON ; détails docs/matrice-parametres-zoom-temps.md §12) : filamentarité type toile cosmique à a=1 (transformée ridged passe-bande <150 Mpc — uniformité physique aux Gpc, mêmes graines/phases ; **changera l'aspect a=1 de la production**, assumé) ; ton moyen des layers GRF abaissé vers 30–45/255 (cascade sur le ton dissous partagé et le plancher localgroup) ; dissolution FILAMENTAIRE en remontant le temps (chaque keyframe régénérée en FFT avec paramètres dépendant de a — lissage croissant, filamentarité relâchée — au lieu de la seule modulation d'amplitude v2) ; nouveau layer de zoom `milkyway_hires` (ligne A, sprites 1024² cadrage serré 4 rayons). **Nomenclature portée à 13 lignes A..M** (un layer = un visuel unique = un code unique ; règle de permanence : les lettres ne sont jamais redécalées, un futur layer prend la lettre libre suivante ; l'ancien C=l1b devient D).

- **16 juillet — moteur v3.2 validé : advection de Zel'dovich** (variante Z2 choisie sur grille de 10 ; blocs `zeldovich` + `web_ambient` du JSON, doc matrice §12.e). La densité des layers de champ = dépôt CIC d'une grille de masse advectée par Ψ=ik δ̂/k² (bande 6 px → 150 Mpc, S=11 px à a=1) — les caustiques remplacent crêtes ET log-normale ; loi temporelle unique S(s,a)=11·A(s,a)^q (dissolution = dénouement exact des caustiques, uniformité exacte à S=0) ; ancrages injectés dans δ avant advection (gs=1.0) ; toile ambiante diffuse sous A/B/C (texture D échantillonnée, screen 0.12/0.20/0.35, continuité C/D automatique). Recuisson complète en attente (prévisualisation de contrôle d'abord).

- **18 juillet — v3.3 spécifiée puis cuite** (retours sur la v3.2 déployée, doc matrice §12.f) : α résolu par keyframe (luminosité moyenne CONSERVÉE pendant la dissolution, état dissous = fond uni 38/255 partagé — fini le passage au noir pré-embrasement) ; **Ψ comobile unique** (cohérence inter-zoom des caustiques par construction, G global calibré sur la Z2 validée) ; **narration de condensation** (`galaxy_formation` a_form_sprites=0.75 : nuages d'abord, galaxies ensuite) ; toile ambiante ×~1.6, moyenne de zone en minification, canvas adaptatif 300→640, codes A..M affichés dans le prototype.

**Pas encore fait** : aucune intégration en production (`DensityLayer.tsx`, `RealGalaxiesLayer.tsx`) — tout reste dans `app/public/*-test.html`, séparé de l'app réelle. L'ancrage résiduel §4.8/§11.4.d est intégré dans les frames `st_localgroup_*` de la matrice mais PAS dans `density_localgroup.png` de production. Le traitement temporel de la texture `milkyway` reste à définir (le prototype la remplace par son sprite N-corps, cf. docs/matrice-parametres-zoom-temps.md §8).

---

## 12. Résumé des formules clés (aide-mémoire)

```
Facteur d'échelle :        a(t) = (Ωm/ΩΛ)^(1/3) · sinh²ᐟ³( (3/2)√ΩΛ H0 t )
Dilution de densité :      ρ(t) = ρ₀ / a(t)³
Horizon des particules :   χ_part(t) = ∫₀ᵗ c dt' / a(t')
Sphère de Hubble :         R_Hubble(t) = c / H(t)
Horizon des événements :   D_event(t) = a(t) · ∫ₜ^∞ c dt' / a(t')
Distance propre à t :      d_propre(t) = a(t) · d_comobile
Champ log-normal :         δ_LN(x) = exp(δ_G(x) − σ²/2) − 1
Compression spatiale :     effectiveHalfWidthMpc = halfWidthMpc / a(t)   [si échelle ≳ 15-30 Mpc, §11.4.e]
Amplitude de structure :   A(s,a) = 1 si a≥1, sinon smoothstep( (log10(a) − log10(a_form(s)) + w(s)) / 2w(s) )
                            avec w(s) = max(−log10(a_form(s)), 0.05)   [ADAPTATIF par échelle, §11.4.b]
Mélange de sources :       combiné = 1 − (1−A)(1−B)(1−C)...   ["screen", jamais un blend RGB, §11.3]
Embrasement :               whiteChannel(a) = 1 − exp(−(bgLateFade(a)^5 × 18))   [§11.4.c — pas un blend de couleur]
```

Paramètres : H0 = 67,4 km/s/Mpc, Ωm = 0,315, ΩΛ = 0,685, Ωr = 9,24×10⁻⁵ (Planck 2018).

---

## 13. Processus de développement et de validation (travail génératif/visuel)

**Contexte** : établi le 9 juillet après un bug de saturation critique (sprites de dissolution complètement cramés) qui a survécu à une "correction" présentée comme validée — la vérification ne portait que sur des courbes de paramètres d'entrée, jamais sur le rendu final réellement calculé. Le bug n'a été trouvé qu'après un second retour visuel de l'utilisateur.

### 13.1 Principe

**Ne jamais présenter un résultat visuel/génératif comme corrigé sur la seule base d'une relecture de code ou d'une vérification des courbes de paramètres.** Calculer et inspecter le résultat RÉELLEMENT rendu, avec des vérifications numériques objectives, avant de demander une confirmation visuelle. Le retour visuel de l'utilisateur doit être une confirmation finale — pas la méthode de détection de bug.

Ce n'est pas un système à agents multiples en parallèle (pas d'outil de ce type disponible) — c'est une discipline à appliquer systématiquement à chaque tâche générative, en une seule passe mais rigoureuse.

### 13.2 Méthode

Pour toute modification touchant un rendu visuel (courbe de temps, texture générée, sprite, palette de couleur...) :

1. **Construire ou réutiliser un script headless** qui réplique EXACTEMENT les calculs du code réel (pas une approximation) — Python (numpy/scipy/PIL) dans cet environnement, `node-canvas` n'étant pas installable (dépendances natives absentes). Un script par mécanisme, dans `scripts/dev/`, maintenu à jour en même temps que le code qu'il valide.
2. **Calculer le résultat sur toute la plage pertinente** (plusieurs valeurs du paramètre qui varie), pas un seul point.
3. **Vérifier objectivement, par le calcul** :
   - **Saturation** : fraction de pixels proches du minimum/maximum (ex. `>240` ou `<8` sur 255) — un taux élevé signale un possible écrasement de la texture/du signal.
   - **Continuité** : pas de saut brutal de moyenne/écart-type entre deux échantillons voisins du paramètre qui varie.
   - **Contraste interne dans les zones d'intérêt** : isoler spécifiquement une zone (ex. un sprite) et mesurer sa variation interne — une moyenne globale saine peut masquer une zone locale totalement plate ou totalement saturée (piège rencontré le 9 juillet : la saturation d'un sprite était invisible dans les statistiques globales de la scène, noyée par le reste de l'image).
   - **Conditions aux limites** : la valeur au point de référence actuel (ex. a=1, "aujourd'hui") doit être identique au rendu de production déjà calibré ; les points de convergence documentés (§11.4.c) doivent être effectivement atteints.
4. **Ne déployer et demander un retour visuel qu'après que ces vérifications passent.**

### 13.3 Défauts déjà rencontrés à vérifier systématiquement (liste vivante)

- Un facteur d'atténuation "cosmétique" (ex. `1/√x`) qui semble réduire une valeur mais reste très insuffisant face à une accumulation (ex. des milliers de particules superposées) — toujours vérifier l'ordre de grandeur RÉEL du pic, pas seulement le sens de variation.
- Une modulation multiplicative (ex. bruit filamenteux) appliquée à un signal déjà saturé : elle ne peut rien montrer une fois la valeur de base à son maximum — l'ordre des opérations compte (lever la saturation AVANT d'espérer voir une texture).
- Une fenêtre de transition étroite juste avant une borne (ex. juste avant la recombinaison) : peut créer un creux ou un saut au lieu d'un fondu — préférer réutiliser une courbe déjà lisse existante plutôt que d'en construire une nouvelle isolée.
- Une normalisation recalculée indépendamment à chaque échantillon (ex. percentiles par image) : peut annuler artificiellement l'effet qu'on cherche à observer — figer la normalisation une fois, la réutiliser pour tous les échantillons comparés.

### 13.4 Rappel — ce que Claude ne peut pas faire

Pas de mode "plusieurs agents Claude en parallèle" pour développer/tester/valider séparément. Un seul thread d'exécution, dans l'ordre. Pas de modification directe du prompt système (fixé par Anthropic/la configuration du projet) — un rappel du principe ci-dessus peut être ajouté aux instructions personnalisées du projet par l'utilisateur, et/ou à la mémoire persistante de ce projet (déjà fait le 9 juillet).
