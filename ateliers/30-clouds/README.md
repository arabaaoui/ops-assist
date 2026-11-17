# Atelier 30 — Les clouds pour l'IA

## Objectif

Vous comparez des lieux d'exécution pour un assistant d'incident fictif.
Vous inspectez les profils sans réseau ni identifiant et changez de profil avec une variable.

## Notions rappelées

Une API managée expose un modèle exploité par un fournisseur via son service partagé.
Un cloud dédié ici désigne un service IA configuré dans votre compte cloud :
cela ne garantit ni matériel exclusif ni absence de traitement partagé.
Sur site, vous exploitez le modèle sur votre infrastructure ; `local` en est une démonstration.
Une passerelle reçoit les requêtes et les route vers un ou plusieurs fournisseurs.
La confidentialité dépend des données envoyées, des contrats, des journaux et des accès.
La résidence dépend des régions, du type de déploiement et des règles du fournisseur.
Un profil ne prouve pas que toutes les données restent dans une région donnée.
La latence inclut transport, attente et génération ; mesurez-la dans votre contexte.
Le coût peut inclure jetons, infrastructure, réseau et exploitation ; comparez les usages.

## Étapes hors ligne

Depuis la racine, listez les profils sans démarrer de modèle :

```bash
uv run ops-assist profiles
OPS_ASSIST_PROFILE=vertex uv run ops-assist profile
OPS_ASSIST_PROFILE=azure uv run ops-assist profile
```

Résultat attendu : la liste présente lieu, résidence indicative et variables manquantes.
Les deux commandes suivantes affichent les modèles et l'état des variables, sans valeurs.
Le changement de profil utilise seulement `OPS_ASSIST_PROFILE` ; chaque profil distant
nécessite toutefois sa propre configuration et les autorisations de son fournisseur.
Une surcharge `OPS_ASSIST_MODELS` désactive le contrôle des variables du profil.

Exécutez les vérifications simulées :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_cloud_profiles.py
```

Résultat attendu : tous les tests passent sans appel réseau ni modèle réel.
Ils contrôlent chaque variable requise et l'arrêt avant l'appel si elle manque.

## Configuration facultative d'un cloud

Pour `vertex`, définissez `VERTEXAI_PROJECT` et `VERTEXAI_LOCATION` et configurez ADC.
ADC est une chaîne de recherche d'identifiants ; elle n'est pas vérifiée hors ligne.
Pour `bedrock`, définissez `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` et
`AWS_REGION_NAME`, ainsi que `AWS_SESSION_TOKEN` pour des identifiants temporaires.
L'exemple Bedrock utilise un profil d'inférence susceptible de traverser des régions.
Pour `azure`, définissez `AZURE_API_KEY`, `AZURE_API_BASE` et `AZURE_API_VERSION`.
Le nom `gpt-4o` doit correspondre au nom de votre déploiement Azure ; sinon adaptez
le profil dans un fichier de profils personnalisé via `OPS_ASSIST_PROFILES_FILE`.
Vérifiez disponibilité, droits, résidence et coûts avant tout appel distant.
Les valeurs ne doivent jamais figurer dans un fichier versionné.

Avec un accès déjà configuré, vous pouvez comparer une question fictive :

```bash
OPS_ASSIST_PROFILE=vertex uv run ops-assist ask 'Explain a fictional latency spike.'
```

Résultat attendu : une réponse du modèle, ou un message d'erreur de configuration.
Cette étape facultative utilise le réseau et peut être facturée.

## Exercices

1. Relevez les variables manquantes pour les trois profils cloud sans afficher leur valeur.
2. Comparez confidentialité, latence et coût pour local, API managée et cloud.
3. Expliquez pourquoi le profil Bedrock ne garantit pas une région unique.
4. Choisissez un critère de résidence et indiquez comment le vérifier avant utilisation.

## Pour aller plus loin

Comparez les conditions et régions de vos services avant de leur transmettre des données.
Hors ligne, dessinez le trajet des données pour chaque profil et pour la passerelle.
