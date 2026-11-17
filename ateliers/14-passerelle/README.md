# Atelier 14 — La passerelle d'IA

## Objectif

Vous placez une porte commune devant les modèles et observez les conséquences d'un repli.
Le parcours principal fonctionne hors ligne, sans proxy, clé ni modèle.

## Notions

Une passerelle reçoit les appels et route un alias vers un fournisseur.
Elle centralise les clés fournisseurs, les quotas, les budgets et les traces.
Le client ne connaît que l'adresse du proxy et sa clé virtuelle.
Un repli peut changer le coût, la latence et les réponses : il doit rester visible.
Le repli ADK est côté client ; celui du proxy est une configuration indépendante.
ADK essaie le modèle suivant sur 429, 500, 502, 503 ou 504 avant toute sortie.
Une erreur de connexion ou un échec après le premier fragment ne déclenche pas ce repli ADK.
La passerelle peut envoyer les mêmes données à un autre fournisseur : vérifiez vos autorisations.

## Étapes hors ligne

1. Examinez les profils et la configuration, sans ouvrir de connexion :

   ```bash
   uv run ops-assist profile --list
   OPS_ASSIST_PROFILE=gateway uv run ops-assist profile
   cat deploy/litellm/config.yaml
   ```

   Attendu : `gateway`, `openai/ops-primary` et l'adresse locale du proxy.
   L'alias primaire vise Gemini et le secours OpenAI, deux fournisseurs distincts.

2. Exécutez le test du repli ADK sur des clients fictifs :

   ```bash
   OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_gateway.py
   ```

   Attendu : le premier client échoue en 503, le second répond ; un avertissement nomme les deux.
   Aucun proxy ni modèle n'est démarré, et aucune clé n'est nécessaire.

3. Comparez l'affichage du modèle à la configuration :

   `ask` affiche sur stderr le champ `model` de la réponse ; `investigate` affiche les versions reçues pendant l'enquête.
   Attendu : le modèle déclaré par le fournisseur apparaît, ou `unknown` s'il ne le fournit pas.
   Un alias renvoyé par un proxy ne prouve pas quel fournisseur a répondu.
   Le repli interne du proxy n'est pas détectable fiablement depuis ces seules réponses : consultez ses traces.

## Essai local facultatif

Ce parcours exige `litellm[proxy]`, PostgreSQL, des clés fournisseurs et peut entraîner des frais.
Installez les extras dans un environnement séparé après avoir examiné leurs dépendances.
Configurez `DATABASE_URL`, `LITELLM_MASTER_KEY`, `GEMINI_API_KEY` et `OPENAI_PROVIDER_API_KEY` hors du dépôt.
Ne réutilisez pas la clé fournisseur OpenAI comme clé virtuelle du client.
Démarrez PostgreSQL et initialisez la base selon la version du proxy installée.

```bash
litellm --config deploy/litellm/config.yaml --host 127.0.0.1 --port 4000
```

Attendu : le proxy écoute localement sur le port 4000.
Créez une clé virtuelle avec `POST /key/generate`, authentifié par la clé maître.
Le corps d'exemple dans le YAML limite les deux alias, le budget sur 30 jours, les requêtes et tokens par minute.
Conservez la clé retournée hors du dépôt, puis injectez-la dans `OPENAI_API_KEY` côté client.

```bash
OPS_ASSIST_PROFILE=gateway uv run ops-assist ask "Qu'est-ce que la latence ?"
```

Attendu : une réponse et le modèle déclaré sur stderr ; l'appel utilise réellement le réseau et peut coûter de l'argent.
Les journaux de dépenses nécessitent la base ; `turn_off_message_logging` désactive les contenus dans les callbacks LiteLLM.
Ne lancez pas le mode debug et vérifiez aussi la configuration des journaux de votre hébergeur et des fournisseurs.
Les métadonnées et les messages peuvent rester visibles ailleurs ; ne transmettez que des données autorisées.

## Exercices

1. Repérez les deux alias et leurs identifiants fournisseurs dans le YAML.
2. Expliquez pourquoi un secours peut modifier une réponse ou sa facture.
3. Changez sur une copie du corps de création de clé le budget et les limites par minute.
4. Imaginez une réponse qui ne contient qu'un alias : comment confirmer le fournisseur effectif ?

## Pour aller plus loin

Comparez les politiques de conservation et les garanties de chaque fournisseur avant de router des données sensibles.
Mesurez le coût et la qualité sur un jeu de données fictif avant de modifier une chaîne de production.

## Bilan du module 2

Les outils donnent accès aux observations ; MCP les expose au-delà du processus.
Les skills décrivent des méthodes, A2A délègue à un agent, et les rôles définissent les frontières.
La sécurité encadre les actions ; la passerelle organise les appels aux modèles et leur gouvernance.
