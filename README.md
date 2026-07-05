# Carte interactive de l'univers observable

Application web représentant l'univers observable en coupe 2D, avec deux axes de navigation indépendants :
- **Zoom spatial** : de la Voie lactée jusqu'à ~95 milliards d'années-lumière (taille actuelle de l'univers observable).
- **Temps** : du découplage matière-rayonnement (~380 000 ans après le Big Bang) jusqu'à aujourd'hui.

L'application représente également trois sphères cosmologiques distinctes (horizon des particules, sphère de Hubble, horizon des événements) et leur évolution dans le temps.

## Structure du repo

- `/app` — Frontend (carte interactive, curseurs, rendu)
- `/scripts` — Précalculs Python (tables cosmologiques, génération des champs de densité de matière)
- `/docs` — Documentation de référence (document d'architecture)

## Documentation

Voir [`docs/architecture-univers-observable.md`](docs/architecture-univers-observable.md) pour le document d'architecture complet (système de coordonnées, modèle cosmologique, layers de densité, sphères cosmologiques, plan d'animations).

## Statut

Projet en phase de conception / démarrage du développement (voir le plan de développement par phases dans les échanges de cadrage du projet).
