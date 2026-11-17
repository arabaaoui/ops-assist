# Atelier 40 — Anatomie d'un système prêt pour la production

## Objectif

Vous allez examiner un agent avec quatre questions opérationnelles.
Cet atelier correspond au chapitre 41 et fonctionne entièrement hors ligne.
Vous produirez une revue de votre propre agent et un bilan du module 6.

## Notions rappelées

Une architecture décrit les composants et leurs frontières de confiance.
Une capacité est utile à connaître avec les données et systèmes qu'elle peut toucher.
Une preuve de test concerne les cas exécutés, pas tous les comportements possibles.
Les traces et le journal d'audit expliquent une partie des actions effectuées.
Leur collecte, leur expurgation et leur conservation ont des limites.
Un arrêt d'urgence et un retour à une version connue demandent des procédures testées.
Le retour arrière de l'agent et celui d'un service enquêté sont deux opérations distinctes.

## Étapes

1. Lisez la revue depuis la racine du dépôt :

```bash
cat docs/production-review.md
```

Résultat attendu : quatre questions, un diagramme, des preuves et des lacunes.
La revue ne déclare pas le système prêt pour un environnement réel.

2. Vérifiez les droits et les limites de l'agent :

```bash
rg -n 'TOOL_ACCESS|ALLOW_WRITES|confirmation' src/ops_assist/security.py
```

Résultat attendu : les outils sont classés et une écriture exige une confirmation.
La lecture seule est le défaut ; le rejeu ne modifie qu'un état simulé.

3. Consultez les vérifications et les traces :

```bash
cat src/ops_assist/evals/threshold.yaml
rg -n 'audit|redact' src/ops_assist/security.py
```

Résultat attendu : un seuil pédagogique et un journal d'audit sont documentés.
L'expurgation est heuristique et les traces optionnelles ne contiennent pas tout.

4. Vérifiez la revue sans réseau ni modèle :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/pytest -q tests/test_production_review.py
```

Résultat attendu : les liens relatifs existent et le diagramme a un type reconnu.
Ce contrôle minimal ne remplace pas un rendu ni une revue de fond.

5. Appliquez les quatre questions à votre propre agent sur une copie locale.
Pour chaque réponse, indiquez une preuve, sa limite et un responsable fictif.
Décrivez comment arrêter l'agent et revenir à une version connue.
Résultat attendu : une liste de lacunes classées avant déploiement et après lancement.
Si vous n'avez pas d'agent, utilisez le squelette et les tests fournis dans le dépôt.

## Exercices

1. Identifiez une donnée non fiable et la frontière qui la sépare des instructions.
2. Choisissez un test et expliquez ce qu'il ne démontre pas.
3. Rédigez une procédure d'arrêt et de restauration pour un service fictif.
4. Classez trois lacunes par criticité et délai avec un responsable fictif.

## Pour aller plus loin

Hors ligne, comparez votre revue au catalogue et à la revue des échecs.
Réévaluez-la après chaque modification importante de l'agent ou de ses accès.

## Bilan du module 6

Vous avez relié évaluations, traces, sécurité, livraison et gouvernance à des preuves.
Une mise en production demande encore des responsabilités et des procédures vérifiées.
