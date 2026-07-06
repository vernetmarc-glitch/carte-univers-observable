# Architecture — Carte interactive de l'univers observable
### Document de référence technique et scientifique
Version 1.0 — Juillet 2026

---

## 0. État actuel du projet — résumé pour reprise de contexte

*(Section mise à jour le 6 juillet 2026, pensée pour permettre à Claude de reprendre ce projet dans une nouvelle conversation sans relire tout l'historique.)*

**Dépôt et déploiement**
- Dépôt : `vernetmarc-glitch/lheure-de-senivrer` (renommé depuis `carte-univers-observable`)
- Site en ligne : https://vernetmarc-glitch.github.io/lheure-de-senivrer/
- Outil de calibration de style : https://vernetmarc-glitch.github.io/lheure-de-senivrer/glow-test.html
- Déploiement automatique via GitHub Actions (`.github/workflows/deploy.yml`) sur push vers `main`
- Projet installable en PWA (`manifest.json`, icônes générées depuis le logo fourni), nom affiché "L'Heure de s'enivrer"

**Architecture de rendu actuelle**
- App plein écran (pas d'onglets, pas de légendes texte) : titre en haut à gauche, bouton réglages (⚙) en haut à droite (style + présence du fond), curseur de zoom vertical à droite, curseur de temps horizontal en bas — tous en overlay sur la carte, avec `env(safe-area-inset-*)`.
- Zone de rendu clampée à un ratio max de 2,4:1 (bandes noires fixes au-delà) pour éviter qu'un layer ne "disparaisse" sur écrans très larges/étroits.
- Canvas dimensionnés selon `devicePixelRatio` (plafonné à 3) pour la netteté sur écrans Retina.
- Chargement des textures progressif et priorisé (le layer du zoom courant en premier, affichage dès l'arrivée de chaque texture), avec indicateur discret en bas à droite.

**Les layers (du plus proche au plus lointain)**
1. `milkyway` : rendu en direct (étoiles individuelles) via le modèle `GalaxyModel` **partagé** (CDN jsDelivr depuis le dépôt `le-silence-du-cosmos`, **ne jamais dupliquer/modifier localement** — toute évolution doit être poussée sur ce repo). Bord du disque à fondu progressif (pas de coupure nette).
2. `localgroup` : texture statique pour les galaxies **procédurales** (halo dépendant de la distance) + rendu en **points individuels** pour les galaxies **réelles** (Andromède, M33, Nuages de Magellan, Naine du Sagittaire, NGC 6822, IC 10, Leo I), chacune avec sa propre morphologie (spirale, spirale barrée, irrégulière avec aile tidale, elliptique étirée...) — cf. `nearbyGalaxyStars.ts`. Les galaxies réelles restent visibles à la fois sur ce layer ET sur le layer `milkyway` (catalogue partagé via `useRealGalaxyCatalog.ts`).
3. `l1b` → `l5` : **10 layers procéduraux** de densité (doublé depuis 5 initialement) : l1b, l2, l2b, l3, l3b, l4, l4a, l4b, l5a, l5. Les paliers "a"/"b" sont des paliers **techniques** (pas de nouveaux layers scientifiques). Chaque palier hérite directement de son plus proche **ancêtre scientifique** (pas du palier précédent en cascade) pour éviter la dilution de structure à grande échelle — poids de combinaison 0,74 (hérité) / 0,67 (détail neuf).

**Fichiers de génération (Python, dans `/scripts`)**
- `generate_layers.py` : génère les 10 textures procédurales (résolution 1024, marge de génération ×1,5 — ×2,4 pour L5 spécifiquement, seul layer visible pile à son bord extrême)
- `generate_local_group_texture.py` : texture des galaxies procédurales du Groupe Local
- `generate_local_group_catalog.py` : catalogue JSON (98 galaxies, réelles + procédurales)
- `local_group_style.py` : **source unique** des constantes de rendu des galaxies réelles (taille de halo, suppression de bruit local...) — ne jamais redéfinir ailleurs

**Point de vigilance connu — synchronisation manuelle requise**
`app/public/glow-test.html` est un fichier HTML autonome (pas de build partagé) qui **duplique manuellement** la liste des layers et leurs marges. Toute évolution de la liste de layers côté production (`DensityLayer.tsx`) doit être répercutée à la main dans cet outil, sinon il se désynchronise silencieusement (déjà arrivé une fois).

**Chantier en attente, déjà cadré (cf. §9 ci-dessous)**
Implémenter la distension spatiale réelle en fonction du temps (a(t)) : actuellement la carte est en coordonnées comobiles fixes (rien ne bouge avec le temps, seule la luminosité change). Le principe retenu et la formule sont déjà documentés en détail au §9 — reste à l'implémenter. Une question adjacente (mise de côté pour l'instant) : la croissance des structures (formation hiérarchique bottom-up) n'est pas non plus implémentée.

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

### 4.1 Découpage en 5 layers, avec plages de validité en échelle comobile

| # | Layer | Échelle (Mpc comobile) | Échelle (années-lumière) | Nature de la structure |
|---|---|---|---|---|
| 1 | Local | 0 – 3 | 0 – 10 millions | Voie lactée, Groupe Local — positions réelles connues, pas de génération statistique |
| 2 | Amas de galaxies | 3 – 30 | 10 – 100 millions | Amas, fonction de corrélation croissante |
| 3 | Toile cosmique | 30 – 150 | 100 – 500 millions | Filaments, murs, vides ; distance caractéristique inter-superamas ~120-140 h⁻¹ Mpc |
| 4 | Transition vers l'homogénéité | 150 – 300 | 500 Ma – 1 Ga | Zone de fondu entre structure et uniformité ("End of Greatness" débattu entre 100 et 300 Mpc) |
| 5 | Univers homogène | 300 – 14 400 | 1 Ga – 47 Ga (rayon) | Densité uniforme extrapolée, conforme au principe cosmologique |

### 4.2 Mécanisme de transition entre layers (zoom)

- Chaque layer est un canvas/texture indépendant.
- Au passage d'une plage de validité à l'autre, un **fondu d'opacité** (crossfade) est appliqué entre le layer sortant et le layer entrant, sur une zone tampon (~10-20% de recouvrement autour de la frontière).
- Le layer 1 (local) n'est pas généré procéduralement — c'est une carte de positions réelles (catalogue simplifié du Groupe Local).

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

### 4.4 Héritage entre layers (exigence initiale du projet)

**Principe : un seul champ gaussien de base par région, décliné en plusieurs résolutions par filtrage passe-bas successif — pas un champ indépendant par layer.**

- Layer 5 (homogène) → Layer 4 → Layer 3 → Layer 2 : chaque niveau ajoute des fréquences plus hautes (détails plus fins) au-dessus de la structure déjà présente au niveau parent, en réutilisant les mêmes phases aléatoires.
- Techniquement : filtres gaussiens/passe-bas à des coupures d'échelle croissantes (analogue aux filtres à 4, 2, 1 h⁻¹ Mpc utilisés en recherche pour visualiser la toile cosmique à plusieurs résolutions), soit encore une approche "multi-octaves" calée sur P(k) plutôt que sur un bruit arbitraire.
- Conséquence pratique : quand on zoome sur une région, le layer plus détaillé n'invente pas une nouvelle distribution — il **précise** celle déjà visible au zoom précédent.

### 4.5 Interaction zoom × temps

Le facteur de dilution 1/a³ (§3.3) s'applique **après** la génération spatiale du champ de densité — il est indépendant de l'échelle affichée. Le champ de densité de base est généré à z=0 (aujourd'hui) ; on le dilue ensuite dans le temps.

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

## 10. Résumé des formules clés (aide-mémoire)

```
Facteur d'échelle :        a(t) = (Ωm/ΩΛ)^(1/3) · sinh²ᐟ³( (3/2)√ΩΛ H0 t )
Dilution de densité :      ρ(t) = ρ₀ / a(t)³
Horizon des particules :   χ_part(t) = ∫₀ᵗ c dt' / a(t')
Sphère de Hubble :         R_Hubble(t) = c / H(t)
Horizon des événements :   D_event(t) = a(t) · ∫ₜ^∞ c dt' / a(t')
Distance propre à t :      d_propre(t) = a(t) · d_comobile
Champ log-normal :         δ_LN(x) = exp(δ_G(x) − σ²/2) − 1
```

Paramètres : H0 = 67,4 km/s/Mpc, Ωm = 0,315, ΩΛ = 0,685, Ωr = 9,24×10⁻⁵ (Planck 2018).
