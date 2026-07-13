# Génération de la matrice de visuels temps × zoom — L'Heure de s'enivrer

## Contexte

Lis d'abord `docs/architecture-univers-observable.md` en entier, en particulier :
- §0 (état actuel du projet)
- §4 (système de layers spatiaux) et §4.7 (portée de l'ancrage du Groupe Local)
- §9 et §11 (matrice de cohérence spatio-temporelle — équations, tableau de paramètres par layer)
- §13 (processus de développement et de validation — **obligatoire**, lis-le avant de produire quoi que ce soit)

Ce prompt complète et précise §11 à la lumière de plusieurs itérations de prototypage déjà réalisées (voir liste des prototypes en §11.5 et les scripts `scripts/dev/`). Certaines valeurs ci-dessous corrigent ou affinent ce qui est écrit dans le document — en cas de divergence, ce prompt fait foi pour la génération de la matrice, mais **mets à jour le document d'architecture en conséquence une fois le travail terminé**, pour que la prochaine instance n'ait pas à redécouvrir ces mêmes points.

## Objectif

Générer, en une fois, un ensemble cohérent de visuels permettant de naviguer librement sur deux axes — le zoom (layers spatiaux, de la Voie lactée à `l5`) et le temps (`a(t)`, d'aujourd'hui à la recombinaison) — sans rupture visuelle en changeant d'axe à n'importe quel point de la grille.

## Les deux seuls types de contenu graphique

Il n'existe que deux types de contenu, jamais un troisième :

1. **Sprites de galaxies** — Voie lactée + 8 galaxies réelles nommées (Andromède, Triangulum, Grand/Petit Nuage de Magellan, Naine du Sagittaire, NGC 6822, IC 10, Leo I), visibles individuellement sur les layers de bas niveau de zoom (`milkyway`, `RealGalaxiesLayer`, éventuellement `localgroup` pour les positions).
2. **Layer de champ de densité** — plus ou moins condensé (pics nets) ou filamenteux/vaporeux ou uniforme, présent sur **tous** les layers, à toute époque, y compris sous les sprites.

Aucun troisième mécanisme n'est permis : pas de calque de flou, pas de calque de couleur unie séparé, pas de vignette, pas d'effet de post-traitement générique. Toute variation visuelle doit provenir des **paramètres de génération** de ces deux types de contenu.

## Règle de composition — à respecter strictement

Chaque source de contenu (sprites/points, champ de densité, embrasement) est calculée **indépendamment**, chacune passant par sa propre transformation non linéaire de type `tone = 1 - exp(-champ_brut)` (ou l'équivalent log-normal de production, `field_to_log_density`). Les sources sont ensuite combinées par un mélange type **"screen"** :

```
combiné = 1 - (1 - source_A) × (1 - source_B) × (1 - source_C) × ...
```

**Jamais** :
- de flou gaussien (`blur()`, `gaussian_filter`, ou équivalent) appliqué après coup pour fondre des éléments entre eux ou pour "adoucir" une transition ;
- d'atténuation globale d'un layer vers une couleur/valeur unie pour le faire disparaître ou pour le faire apparaître ;
- d'addition de plusieurs champs bruts dans un même buffer avant une transformation commune UNIQUEMENT si cela mélange des sources qui doivent rester indépendamment nettes (l'addition avant transformation reste correcte quand c'est la même nature de contenu — ex. plusieurs galaxies dans une même scène).

Toute impression de "disparition" ou d'"uniformisation" doit venir du fait que les **paramètres de génération** du champ de densité convergent vers un état plat (amplitude → 0 avant la transformation non linéaire), jamais d'un mélange de couleur après coup.

## Génération du champ de densité — technique imposée

**Un champ de bruit interpolé en douceur (grille de valeurs + interpolation bilinéaire/smoothstep, type Perlin/value-noise) est INTERDIT**, même sans aucun flou explicite. Ce type de bruit est un filtre passe-bas par construction (vérifié par calcul : la variance du laplacien s'effondre à quasi zéro dès qu'on tente de le faire "grandir" par zoom, quelle que soit sa résolution source, y compris à 8192×8192).

**Technique imposée** : champ gaussien contraint par un spectre de puissance réaliste (FFT), exactement la méthode déjà utilisée en production pour `l1b`→`l5` (`generate_raw_field` dans `scripts/generate_layers.py`) :
1. Un champ "maître" haute résolution est généré une fois (FFT + P(k), formule de transfert Eisenstein & Hu).
2. Pour donner l'impression de croissance d'échelle des filaments dans le temps : recadrer une portion de plus en plus petite du champ maître (donne les grandes structures qui "grandissent"), **plus** un détail haute fréquence **fraîchement régénéré** à pleine résolution d'affichage à chaque palier temporel (jamais un simple agrandissement du recadrage seul — vérifié : sans détail frais, le contenu haute fréquence s'effondre au zoom).
3. L'amplitude du champ (avant la transformation non linéaire) diminue avec le temps selon `A(s,a)` (cf. plus bas) — c'est ce qui fait disparaître les pics de densité sans jamais perdre le squelette filamenteux ni recourir à un flou.

Concrètement : cuire hors-ligne une séquence de frames (niveaux de gris, comme tous les sprites du projet — la couleur/palette reste une opération runtime) par palier temporel pertinent, à charger et interpoler comme des sprites classiques. Ne jamais générer ce bruit en direct dans le navigateur avec une grille interpolée.

## Rattachement aux coordonnées physiques — piège déjà rencontré deux fois

Le champ de densité de fond DOIT être échantillonné dans le **même système de coordonnées physiques (Mpc)** que les sprites/galaxies qu'il accompagne, et la fenêtre de mappage à l'affichage doit rester le **champ de vue actuellement affiché** (le demi-champ courant), constante quelle que soit la frame temporelle utilisée — la croissance apparente des filaments est déjà entièrement contenue dans le contenu de chaque frame cuite (cf. section précédente) ; ne surtout pas appliquer un rétrécissement de fenêtre une deuxième fois au moment de l'affichage (ça confine le contenu visible à une zone centrale de plus en plus petite au lieu de remplir le cadre — bug réellement rencontré et corrigé). Vérifier par le calcul, sur toute la grille temps × zoom, qu'aucune zone du cadre affiché ne retombe sur une valeur neutre/par défaut.

## Compression spatiale — bornée par la physique

`effectiveHalfWidthMpc = halfWidthMpc / a(t)` **uniquement** aux échelles où le flux de Hubble domine sur la gravité :
- **Aucune compression** en dessous de ~2 Mpc (Groupe Local, gravitationnellement lié — galaxies, `RealGalaxiesLayer`).
- **Transition douce** entre ~2 et ~15 Mpc (`l1b`).
- **Pleinement active** au-delà de ~15-30 Mpc (`l2` et au-delà).

Utiliser un fondu en S (smoothstep) sur cette transition, jamais une coupure nette.

## Époque de formation par échelle — `a_form(s)`

La dissolution ne suit pas une seule courbe partagée par tout. Chaque groupe d'échelles se dissout autour de SA propre époque de formation physique :

| Échelle | a_form | Base physique |
|---|---|---|
| Sprites (galaxies), `localgroup` | ≈ 0,20 | Demi-masse des galaxies assemblée vers z≈2,5-5 |
| `l1b` | ≈ 0,55 | Zone de transition/retournement des amas |
| `l2` | ≈ 0,65 | Formation des amas, z≈0-1 |
| `l2b` | ≈ 0,70 | idem, légèrement plus tardif |
| `l3`→`l4b` | ≈ 0,92-0,95 | Toile cosmique, encore jeune aujourd'hui |
| `l5a`/`l5` | ≈ 1,0 | Quasi homogène, aucune dissolution significative |

Fonction d'amplitude `A(s,a)` : smoothstep en `log(a)`, centrée sur `a_form(s)`, avec une largeur de transition **adaptative par échelle** (distance en dex entre `a_form(s)` et `a=1`) — pas une largeur fixe, sous peine que `A(s, a=1) ≠ 1` pour les échelles dont `a_form` est proche de 1 (ça changerait un rendu déjà calibré à "aujourd'hui" — bug déjà rencontré et corrigé). Contrainte dure à vérifier par le calcul : **`A(s, a=1) = 1` exactement et continûment, pour toutes les échelles.**

Conséquence directe : les structures filamenteuses apparaissent d'abord aux petites échelles (galaxies, formées tôt) et seulement plus tard aux grandes échelles (amas/toile cosmique, encore jeunes) — c'est cette différence d'époque par échelle qui donne le bon ordre d'apparition, pas un réglage arbitraire par layer.

## Accrétion des galaxies — moteur N-corps

Pour chacun des 9 sprites (Voie lactée + 8 galaxies réelles), simuler la dissolution/accrétion avec un vrai moteur N-corps (Barnes-Hut, quadtree, intégration leapfrog, softening gravitationnel) — pas une approximation procédurale. Déjà implémenté et calibré (`scripts/simulate_dissolution.mjs`, `scripts/generate_dissolution_sprites.mjs`) :

- Position de départ (aujourd'hui) : vraies positions d'étoiles (`GalaxyModel` pour la Voie lactée, générateur de morphologie procédural pour les 8 autres).
- Vitesse initiale : radiale (dispersion) + turbulente (aléatoire) + **tangentielle cohérente** (même sens pour toutes les particules — représente la conservation du moment angulaire : le nuage protogalactique s'est effondré en tourbillonnant pour créer la rotation actuelle).
- Gravité mutuelle laissée active pendant la dispersion (donne des amas irréguliers persistants, pas une explosion uniforme).
- **Conservation du flux obligatoire** quand le rayon d'une particule grandit : l'amplitude doit être divisée par le carré du facteur d'élargissement (pas sa racine), sous peine de saturation — déjà vérifié : sans cette correction, le champ sature dès `a=1`, avant même toute dissolution, à cause du simple chevauchement de milliers de particules.
- Combiner le résultat de cette simulation de particules avec un layer de champ de densité **ancré sur la position réelle de la galaxie** (renflement dont l'amplitude croît vers `a=1`, mélangé par le même opérateur "screen" que le reste) — c'est ce qui fait que le fond se "rattache" visuellement à l'endroit où chaque galaxie s'est réellement formée, pas seulement les points de la simulation.

## Ancrage des galaxies sur les layers de zoom supérieurs

Sur `l1b`/`l2`/`l2b`, les 98 galaxies du catalogue (8 réelles + 90 procédurales) génèrent un ancrage de densité (mécanisme déjà existant, `apply_local_group_anchor`), qui doit désormais aussi être modulé dans le temps par `A(s_galaxie, a)` — c'est-à-dire l'amplitude de structure à l'échelle DES GALAXIES (`a_form≈0,20`), pas celle du layer qui les accueille. L'ancrage reste net tant que les galaxies elles-mêmes sont formées, et se dissout avec elles.

## Embrasement (convergence vers le blanc à la recombinaison)

Pas de calque de couleur séparé. Un décalage (`embrasementOffset`) qui grandit uniquement tout près de la recombinaison est ajouté aux champs bruts (sprites, fond) **avant** leur transformation non linéaire respective, puis combiné par le même mélange "screen" que le reste. Comme la valeur maximale de la palette de couleur (`colorForValue(1.0)`) correspond déjà exactement à la teinte de recombinaison visée, saturer le ton vers 1 suffit — pas besoin de mélanger vers une couleur cible explicite. Calibrer ce décalage (forme de la courbe, amplitude) par le calcul pour qu'il reste nul pendant l'essentiel de la dissolution et ne s'active que dans la toute dernière partie du parcours temporel.

## Palette de couleur — ne pas en inventer une nouvelle

Réutiliser exactement la palette `astro` déjà calibrée (`#000000, #170a05, #4a1f0a, #a8480f, #e8a13a, #fff3d6`) et le fond actuel de l'app (`#05050a`). Toute nouvelle teinte doit être justifiée, pas improvisée.

## L'espace de paramètres à définir AVANT tout rendu

Construire une matrice explicite (zoom × temps), et pour chaque cellule documenter, avant de générer quoi que ce soit :
- Présence ou non de sprites de galaxies individuels, et leur mode de génération (positions réelles GalaxyModel / morphologie procédurale / aucun sur ce layer).
- Niveau de couleur de fond moyen visé (calculable, pas juste estimé à l'œil).
- Paramètres de génération du champ de fond : amplitude avant transformation non linéaire (`A(s,a)`), échelle/recadrage du champ maître, seed.
- Niveau d'ancrage des galaxies et son impact sur la génération du fond (amplitude, rayon d'influence).
- Taux de compression spatiale à appliquer (`effectiveHalfWidthMpc`, borné par la physique — cf. plus haut).
- Poids de fondu entre layers adjacents si plusieurs doivent se superposer à cette cellule précise de la matrice.

Documenter cette matrice (tableau ou structure de données) avant de produire le moindre visuel — c'est elle qui garantit la cohérence, pas une vérification a posteriori.

## Validation — obligatoire, avant tout retour visuel (cf. §13)

Pour chaque mécanisme généré, avant de le présenter comme terminé :
1. Construire un script headless (Python/numpy/scipy — `node-canvas` n'est pas installable dans cet environnement) qui réplique exactement les calculs réels, dans `scripts/dev/`.
2. Calculer le résultat sur toute la plage pertinente (plusieurs valeurs de zoom ET de temps, pas un seul point).
3. Vérifier objectivement : saturation (fraction de pixels proches du min/max), contenu haute fréquence qui ne doit jamais tomber à zéro (variance du laplacien, ou équivalent), continuité entre échantillons voisins (pas de saut ni de creux), couverture complète du cadre à tout zoom/temps (pas de zone neutre/par défaut), et `A(s, a=1) = 1` exactement pour toute échelle.
4. Ne déployer et ne demander un retour visuel qu'après que ces vérifications passent.

## Non-régression

Le rendu à `a=1` (aujourd'hui) doit être strictement identique à la production actuelle déjà calibrée, à tout niveau de zoom. Si un paramètre nouveau change ce rendu de référence, c'est un bug à corriger avant de continuer, pas un détail à ajuster plus tard.

## Question ouverte à traiter avant de commencer

Le document d'architecture (§11.3.c) décrit encore l'ancienne méthode d'embrasement par calque de couleur mélangé (`universeGlowColor` en blend RGB) — remplacée depuis par le décalage-avant-transformation décrit ci-dessus. Mets à jour cette section avant de t'appuyer dessus, pour éviter de reconstruire l'ancien mécanisme par erreur.
