# Atelier 32 — Du SDLC à l'AIDLC

## Objectif

Vous identifiez une version du comportement d'un assistant et vous la reliez à ses évaluations.
Cet atelier fonctionne entièrement hors ligne : aucune clé ni aucun modèle ne sont nécessaires.

## Notions rappelées

Le SDLC organise la conception, le développement, les tests et la livraison du logiciel.
L'AIDLC ajoute la gestion des données, des modèles et des évaluations au cycle logiciel.
Un changement de prompt ou de modèle peut modifier la réponse sans changer le code Python.
Versionnez donc le code, les prompts, les skills, les données, les modèles et les évaluations.
Une version de modèle identifie une configuration, pas une garantie de réponse identique.
Le fingerprint sert d'identifiant de build du comportement, pas de preuve de qualité.
Il résume les prompts, skills, profil résolu, modèles, schéma, scorer et version du jeu.
Les identifiants de modèles et leur ordre comptent, y compris pour le palier rapide.
Les secrets et adresses ne sont pas inclus : gardez-les hors du journal.
Les résultats dépendent aussi des services, données et versions externes non identifiés ici.

## Étapes

1. Installez les dépendances depuis votre environnement déjà préparé, sans accès réseau.
2. Affichez le profil résolu :

```bash
ops-assist profile
```

Résultat attendu : une ligne `Fingerprint:` suivie de 16 caractères hexadécimaux.
3. Retrouvez cette valeur dans la première entrée de `BEHAVIOR_CHANGELOG.md`.
Pour comparer au profil par défaut, retirez les éventuelles surcharges `OPS_ASSIST_*`.
4. Lisez le journal et reliez chaque modification à sa raison et à son évaluation connue.
Les évaluations historiques absentes sont explicitement indiquées comme non enregistrées.
5. Lancez le contrôle hors ligne :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/pytest -q tests/test_fingerprint.py
```

Résultat attendu : les tests passent, sans appel à un modèle.
6. Lors d'un changement de comportement, exécutez `ops-assist profile` avec le profil par défaut.
Ajoutez en tête du journal la date, la valeur, le changement, sa raison et le résultat d'évaluation.
Si vous changez le scorer, augmentez aussi `SCORER_VERSION` dans `fingerprint.py`.
Le test du journal échoue tant que la première entrée ne contient pas la nouvelle valeur.
Les autres profils produisent chacun leur propre valeur et ne remplacent pas l'entrée par défaut.
Les enveloppes de rapports et résultats d'évaluation conservent la valeur de leur configuration.

## Exercices

1. Changez temporairement une instruction du prompt : quelle valeur évolue ? Restaurez le fichier.
2. Comparez le profil par défaut à une surcharge locale de `OPS_ASSIST_MODELS`, sans appeler le modèle.
3. Expliquez pourquoi une clé API différente ne doit pas modifier le fingerprint.
4. Proposez une entrée de journal après une modification fictive du scorer et une évaluation hors ligne.

## Pour aller plus loin

Comparez deux résultats d'évaluation sauvegardés et discutez leurs fingerprints et versions de données.
Sans modèle disponible, étudiez les tests et les exemples du dépôt : ils restent exécutables hors ligne.
Les résultats de tests ne remplacent pas une revue humaine des réponses de l’assistant.
