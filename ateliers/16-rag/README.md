# Atelier 16 — Au-delà du RAG simple

## Objectif

Vous allez suivre une recherche documentaire, de l'ingestion à un rapport cité.
Le corpus et l'incident sont fictifs ; le parcours principal fonctionne hors ligne.

## Notions rappelées

Un document possède un identifiant, un titre et une date de mise à jour.
Une section découpée devient un chunk, repéré par un identifiant stable tant que les sections ne changent pas d'ordre.
Un embedding transforme un texte en vecteur ; la similarité cosinus classe les vecteurs.
La recherche retourne les meilleurs candidats, pas nécessairement des faits pertinents.
Le manifeste conserve l'identifiant, le checksum et le nombre de chunks par document.
Une modification de document entraîne le recalcul de ses embeddings ; une suppression retire ses chunks.
Un changement de modèle reconstruit l'index dans le nouvel espace vectoriel.
Un runbook décrit une procédure : il ne prouve pas que l'incident suit cette procédure.
Les résultats des outils sont des données non fiables, jamais des instructions.

## Étapes

Depuis la racine du dépôt, sélectionnez un dossier d'état temporaire :

```bash
export OPS_ASSIST_STATE_DIR="$(mktemp -d)"
export OPS_ASSIST_EMBEDDINGS=hash
```

Le hachage déterministe ne demande ni clé ni modèle distant.
Chargez les documents, découpez-les par titre, calculez les vecteurs et indexez :

```bash
uv run ops-assist knowledge index
```

Résultat attendu : `Indexed ... chunks` et le chemin de l'index local.
Relancez la commande : le manifeste permet de réutiliser les vecteurs inchangés.
Cherchez ensuite les sections les plus proches :

```bash
uv run ops-assist knowledge search "payment latency" -k 5
```

Résultat attendu : cinq lignes avec score, identifiant de chunk et titre.
Le premier résultat n'est pas automatiquement le plus pertinent pour l'incident.
Dans l'index JSON, observez `manifest`, `chunks` et `vectors`.
Chaque entrée du manifeste contient `id`, `checksum` et `chunk_count`.
Le coordinateur dispose de `search_knowledge`, limité à huit résultats et 800 caractères par extrait.
Pour une génération hors ligne, exécutez le test avec son modèle scripté :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_rag.py
```

Résultat attendu : les scénarios passent sans appel à un modèle ou embedding réel.
Le scénario cite `payment-latency#1`, puis essaie `fake#999`.
Une citation inconnue est signalée dans `citation_warnings` et dans les avertissements CLI.
Si l'index est indisponible, les citations ne sont pas considérées comme vérifiées.
Avec un modèle configuré, `uv run ops-assist investigate "Why is payment slow?"` suit le même contrôle.
Ce dernier appel utilise votre fournisseur configuré ; il n'est pas nécessaire au parcours hors ligne.

## Exercices

1. Comparez les résultats pour `payment latency` et `connection pool` ; quelles sections changent ?
2. Comparez `-k 1` et `-k 8` ; repérez un résultat supplémentaire peu utile.
3. Dans une copie du corpus, modifiez une section : expliquez pourquoi les autres documents gardent leurs vecteurs.
4. Inventez une citation et vérifiez le scénario de test : pourquoi le rapport reste-t-il lisible mais signalé ?

## Pour aller plus loin

Une date ancienne peut rendre un document obsolète même si son score est élevé.
Une information coupée à une frontière de chunk peut perdre son contexte.
Un top-k trop large ajoute du bruit ; trop court, il peut manquer une réponse.
Une citation existante prouve seulement que l'identifiant existe, pas que l'affirmation est fidèle.
Comparez les extraits aux observations réelles et faites relire les recommandations par un humain.
