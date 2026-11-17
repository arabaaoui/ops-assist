# Atelier 36 — CI/CD des agents

## Objectif

Vous allez examiner les barrières de livraison d'un agent et provoquer un échec local.
Cet atelier correspond au chapitre 37 et fonctionne hors ligne après installation des dépendances.
Aucun modèle, registre ou compte n'est nécessaire pour les exercices locaux.

## Notions rappelées

La CI vérifie chaque changement avec des contrôles reproductibles.
Une barrière échouée interdit ici la construction de l'image.
Les tests de contrat vérifient le comportement attendu des sources d'observation.
Les évaluations rapides notent des rapports fictifs déjà enregistrés : elles ne mesurent pas un modèle réel.
Les sondes red team rapides vérifient certaines limites de sécurité sans appel de modèle.
Ces contrôles ne remplacent pas les évaluations lentes sur modèles et fournisseurs réels.
Planifiez ces dernières séparément, avec un budget et un jeu de données appropriés.

## Étapes

1. Installez les dépendances déjà disponibles dans votre environnement :

```bash
uv sync --frozen
```

Résultat attendu : l'environnement correspond au fichier de verrouillage.
Sans accès réseau, utilisez un environnement et un cache déjà remplis.

2. Reproduisez les barrières rapides depuis la racine :

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q tests/test_replay.py tests/test_live_sources.py
uv run --frozen ops-assist eval check-reports tests/fixtures/evaluation/passing
uv run --frozen ops-assist redteam --fast
```

Résultat attendu : chaque commande réussit et les rapports fictifs passent l'évaluation.
La CI exécute aussi toute la suite pytest, dont le scan `FORBIDDEN_TERMS`.
Le secret est requis sur les pushes et les pull requests du dépôt ; les forks n'y ont pas accès.

3. Observez une barrière qui échoue, sans publier de branche :

```bash
uv run --frozen ops-assist eval check-reports tests/fixtures/evaluation/failing
```

Résultat attendu : le rapport échoue et la commande retourne un code non nul.
Pour une démonstration sur branche locale, créez une branche de démonstration et modifiez une copie du rapport dans `tests/fixtures/evaluation/passing` afin de changer son statut attendu.
Relancez la commande sur ce dossier : la barrière doit échouer ; restaurez ensuite le fichier et ne poussez pas la branche.

4. Lisez `.github/workflows/ci.yml` et `Dockerfile`.
Les cinq jobs doivent réussir avant la construction de l'image.
Sur une étiquette de version (`v*`) seulement, pas sur les étiquettes `etape-NN`, l'image est poussée dans GHCR puis signée par digest avec cosign et une identité OIDC.
Les autres événements construisent l'image sans publication ni signature.
Les actions et images de base sont épinglées ; la signature relie le digest à une identité, sans garantir la qualité du contenu.
Le dépôt doit autoriser les permissions et configurer le secret du scan pour que la livraison fonctionne.
La protection de branche et les vérifications requises se configurent séparément dans le dépôt.

## Exercices

1. Identifiez les cinq barrières et expliquez quel défaut chacune peut détecter.
2. Modifiez localement le rapport fictif passant, constatez l'échec et restaurez-le.
3. Comparez le coût et la couverture d'une évaluation hors ligne et d'une évaluation sur modèle réel.
4. Expliquez pourquoi signer un digest est plus précis que signer un nom de tag mutable.

## Pour aller plus loin

Étudiez la vérification de signature avec l'identité et l'émetteur attendus avant tout déploiement.
Un SBOM est facultatif : il inventorie les composants mais ne prouve pas leur sûreté.
Hors ligne, relisez le workflow et repérez les permissions et les références épinglées.
