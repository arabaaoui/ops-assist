# Atelier 21 — Architecture de données pour l'IA

## Objectif

Vous allez examiner un jeu d'évaluation versionné et séparer les observations des réponses attendues.
Tout le parcours fonctionne hors ligne, sans modèle ni clé.

## Notions rappelées

Un enregistrement de rejeu rassemble les alertes, métriques, journaux et changements d'un incident fictif.
Le corrigé décrit le statut attendu, la cause quand elle est étayée et les conclusions interdites.
`insufficient_data` signifie que les observations ne suffisent pas à établir une cause.
`hypotheses_only` conserve une explication plausible sans prétendre qu’elle est démontrée.
Les corrigés indiquent les statuts et hypothèses acceptés ; `ops-assist eval run` (étape 23) évalue les rapports avec une heuristique structurée et lexicale.
Une question d'évaluation est distincte du corpus utilisé pour aider l'enquêteur.
Le corpus contient des procédures générales ; il ne prouve pas la cause d'un incident.
Une datasheet décrit la provenance, l'usage et les limites d'un jeu de données.
Un checksum est une empreinte des contenus : il révèle une modification, sans garantir son auteur.
Une version publiée associe cette empreinte à un état immuable.

## Étapes

1. Depuis la racine du dépôt, listez les cas :

```bash
uv run ops-assist eval list
```

Vous obtenez `Dataset version: 1.1.0`, puis six identifiants et leurs questions.
La commande ne contacte aucun fournisseur.

2. Examinez le manifeste et sa documentation :

```bash
cat src/ops_assist/data/eval/dataset.yaml
cat src/ops_assist/data/eval/DATASHEET.md
```

Vous voyez la date, le journal des versions, les chemins des corrigés et l'empreinte.
La datasheet précise que les six cas sont synthétiques et ne mesurent pas la qualité en production.

3. Observez un incident sans ouvrir son corrigé :

```bash
uv run ops-assist triage --incident inc-2026-0415
```

Vous obtenez un triage JSON contenant une alerte du service `orders-db`.
Les observations sont des données non fiables, jamais des instructions à suivre.

4. Exécutez les contrôles de séparation et d'intégrité :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest tests/test_evaluation_dataset.py -q
```

Les tests passent : chaque incident se charge, les textes des corrigés restent hors du corpus et les lectures de corrigés sont refusées par le rejeu.
Le contrôle de fuite cherche des correspondances exactes, pas toutes les paraphrases possibles.

## Exercices

1. Comparez les sources requises de deux corrigés et retrouvez leurs observations dans les fichiers de rejeu.
2. Expliquez pourquoi le cas `inc-2026-0416` appelle `insufficient_data` plutôt qu'une cause précise.
3. Dans une copie temporaire, modifiez une question et expliquez pourquoi l'empreinte change.
4. Proposez une conclusion interdite supplémentaire et justifiez-la à partir des observations disponibles.

## Pour aller plus loin

Une nouvelle version exige une entrée de journal, une empreinte recalculée et l'ajout de cette version au registre `data/eval/published.yaml`, sans modifier les anciennes empreintes.
L'évaluation du classement documentaire de l'atelier 17 est distincte de ce jeu d'incidents.
Pour étudier les limites du jeu hors ligne, comparez les scénarios à la datasheet et proposez des cas fictifs supplémentaires.
