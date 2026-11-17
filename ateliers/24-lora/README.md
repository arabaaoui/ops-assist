# Atelier 24 — LoRA

## Objectif

Vous préparez un jeu fictif de classification d'alertes hors ligne.
Vous expliquez comment une adaptation LoRA pourrait être évaluée.
L'entraînement et l'appel à un modèle ne sont pas fournis dans cet atelier.

## Notions rappelées

Un modèle préentraîné contient des poids appris sur un grand corpus.
Le fine-tuning adapte ces poids à une tâche et à des exemples donnés.
LoRA conserve les poids de base et apprend des matrices de faible rang.
Leur produit représente une correction ajoutée à certaines couches.
Le rang contrôle la taille de ces matrices : un rang élevé coûte davantage
et peut apprendre plus de détails, sans garantir de meilleurs résultats.
Les adaptateurs sont généralement bien plus petits que le modèle complet.
QLoRA utilise un modèle de base quantifié et entraîne des adaptateurs LoRA.
La quantification réduit la mémoire mais peut modifier la précision.
Le merge fusionne la correction dans les poids du modèle de base.
Il simplifie le déploiement mais produit un nouvel artefact volumineux ;
gardez l'original et vérifiez les effets numériques, surtout après quantification.
Vérifiez les licences du modèle, des données et des bibliothèques :
elles peuvent limiter l'usage, la redistribution ou les usages commerciaux.
Un modèle aux poids accessibles n'est pas nécessairement libre de tout usage.

## Étapes et résultats attendus

1. Depuis la racine du dépôt, générez et inspectez le jeu sans réseau :

   ```bash
   python3 ateliers/24-lora/make_dataset.py > /tmp/ops-assist-alerts.json
   python3 -m json.tool /tmp/ops-assist-alerts.json | head -40
   ```

   Résultat attendu : un objet JSON avec `train` et `test` ;
   chaque exemple contient `text` et `label`.

2. Comptez les exemples et les classes :

   ```bash
   python3 -c 'import json; d=json.load(open("/tmp/ops-assist-alerts.json")); print({k: len(v) for k,v in d.items()}); print(sorted({x["label"] for x in d["test"]}))'
   ```

   Résultat attendu : 21 exemples d'entraînement, 7 de test et cinq classes.
   Les noms et résumés proviennent des alertes fictives du replay ;
   des formulations distinctes produisent les deux partitions.

3. Vérifiez la séparation et le caractère déterministe :

   ```bash
   OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_lora_dataset.py
   ```

   Résultat attendu : les deux tests passent sans appel réseau ni modèle.
   Les textes exacts ne se recouvrent pas, mais les mêmes alertes source
   figurent dans les deux partitions : ce test mesure surtout la reformulation.
   Ce petit jeu ne permet pas d'estimer une généralisation à des incidents inconnus.

4. Préparez une expérience sur papier : réservez des incidents entiers au test,
   choisissez une métrique par classe et gardez le même test pour les deux approches.
   Comparez une prédiction zéro-shot et un modèle adapté avec leurs erreurs.
   Résultat attendu : un protocole qui ne confond pas reformulation et généralisation.
   Tout appel de modèle doit passer par LiteLLM et rester configurable.

## Exercices

1. Expliquez le rôle du rang et son effet sur le nombre de paramètres entraînés.
2. Pourquoi un modèle quantifié peut-il réduire les besoins en mémoire ?
3. Repérez une fuite possible entre partitions et proposez un découpage par incident.
4. Quelles licences et quelles métriques vérifieriez-vous avant une diffusion ?

## Pour aller plus loin

Comparez LoRA et QLoRA sur un GPU avec des données et modèles autorisés.
Documentez les versions, la licence, le coût et les limites du jeu de test.
Lisez la [décision sur le fine-tuning](../../docs/decisions/0002-no-fine-tuning.md).
Le parcours de génération et d'inspection ci-dessus reste entièrement hors ligne.

## Parcours facultatif sur GPU : le carnet

Le carnet `ateliers/24-lora/lora_alert_classifier.ipynb` s'ouvre dans un environnement GPU gratuit en ligne, par exemple Google Colab avec un GPU T4. Il installe des versions épinglées de `transformers`, `peft`, `datasets` et `accelerate`. Il récupère ensuite ce dépôt pour utiliser `make_dataset.py`, puis affine `distilbert-base-uncased` avec LoRA (rang 8, couches d'attention `q_lin` et `v_lin`). Il affiche la part de paramètres entraînables et la précision obtenue sur le jeu de test.

Une dernière cellule, facultative, compare ce résultat à un modèle généraliste interrogé sans entraînement via LiteLLM. Elle utilise votre clé de fournisseur, lue dans les secrets de l'environnement et jamais écrite dans le carnet.

Notez les deux scores obtenus. Le jeu de test reformule les mêmes alertes que l'entraînement : ces chiffres illustrent la méthode, ils ne mesurent pas la généralisation à des incidents inconnus.

Ce carnet télécharge des paquets et un modèle : il n'appartient pas au parcours hors ligne. Les tests du dépôt vérifient seulement qu'il est valide, que ses sorties sont vides, que ses versions sont épinglées et qu'il ne contient aucune clé.
