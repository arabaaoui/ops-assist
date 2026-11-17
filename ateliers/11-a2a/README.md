# Atelier 11 — Déléguer une enquête avec A2A

## Objectif

Vous allez transmettre une question d'incident à un agent distant et examiner sa réponse.
Le parcours de test utilise un modèle scripté et des données enregistrées, sans réseau ni clé.

## Notions

A2A permet à un agent de confier une tâche à un autre agent au moyen de messages.
L'agent destinataire choisit comment mener l'enquête et renvoie son résultat.
Une carte d'agent annonce son adresse, ses formats et ses compétences aux clients.
Ici, la compétence `investigate` décrit une enquête, pas un outil individuel.
La tâche représente le travail et son état ; son résultat peut contenir des artefacts.
Les sessions restent distinctes : seules les informations transmises sont partagées.

MCP et A2A répondent à deux besoins complémentaires :

| | MCP | A2A |
| --- | --- | --- |
| Demande | Appeler un outil précis | Déléguer une question |
| Découverte | Liste d'outils et paramètres | Carte et compétences de l'agent |
| Décision | Le client pilote les appels | L'agent distant conduit son enquête |
| Ici | Lecture des observations sur stdio | Enquête via HTTP local |

Les skills du chapitre précédent décrivent des méthodes dans l'agent ; une compétence de carte A2A annonce un service.
La carte décrit les capacités et, si configurée, le mécanisme d'authentification.
Le contrôle du jeton est effectué par le serveur, et non par la carte.

## Étapes hors ligne

### 1. Examiner la carte

Depuis la racine du projet :

```bash
uv run python - <<'PY'
from ops_assist.a2a_server import build_card
print(build_card(8000))
PY
```

Résultat attendu : `ops_assist`, l'adresse locale, le format texte et la compétence `investigate`.
La carte annonce le port choisi ; le serveur écoute uniquement sur l'interface locale.

### 2. Suivre la délégation sans modèle réel

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_a2a.py
```

Résultat attendu : les tests passent, y compris l'aller-retour entre les deux agents.
Le client HTTP transmet la carte et les messages à l'application ASGI en mémoire.
Le modèle scripté appelle `get_alerts` sur le jeu de données enregistré et renvoie un rapport sourcé.
Le test vérifie la méthode JSON-RPC, la fin de la tâche et le rapport dans un artefact.
Il vérifie aussi les refus sans jeton ou avec un mauvais jeton et la validation du rapport reçu.
Aucun serveur externe, appel réseau ni modèle réel n'est nécessaire à ce parcours.

### 3. Lire les deux côtés

```bash
cat src/ops_assist/a2a_server.py
cat apps/oncall_assistant/agent.py
```

Résultat attendu : `to_a2a` expose l'enquêteur ; `RemoteA2aAgent` transmet la question.
L'assistant d'astreinte délègue directement, sans deuxième modèle, puis valide le rapport.
Une réponse invalide ou un délai dépassé produit une erreur claire.

### 4. Protéger les appels avec un jeton

Définissez `OPS_ASSIST_A2A_TOKEN` dans l'environnement du serveur et dans celui du client.
Utilisez la même valeur secrète dans les deux processus, sans l'inscrire dans le dépôt.
La carte reste lisible sans jeton ; les autres appels exigent `Authorization: Bearer <jeton>`.
Sans variable, le serveur ne demande pas d'authentification.
`OPS_ASSIST_A2A_TIMEOUT` règle le délai total de délégation en secondes (120 par défaut).
Le serveur écoute sur `127.0.0.1` pour limiter l'accès direct à la machine locale.
Pour un accès distant, utilisez un reverse proxy avec TLS et configurez-le pour adapter aussi l’adresse publiée dans la carte.

### 5. Essayer avec votre fournisseur configuré

Cette étape facultative utilise le modèle configuré et peut nécessiter son service ou ses identifiants.
Dans un terminal, démarrez le serveur :

```bash
uv run ops-assist a2a-serve --port 8000
```

Résultat attendu : le serveur annonce une écoute sur `127.0.0.1:8000`.
Dans un autre terminal, lancez `uv run adk web apps` et sélectionnez `oncall_assistant`.
Posez « Pourquoi le paiement est-il lent ? » ; le résultat attendu est un rapport de l'enquêteur.
La variable `OPS_ASSIST_A2A_CARD_URL` permet de choisir une autre URL de carte.
Le serveur A2A utilise les profils et la source configurés pour ops-assist.
Arrêtez les deux processus avec `Ctrl+C` après l'essai.

## Exercices

1. Identifiez le champ qui permet au client de trouver l'adresse du serveur dans la carte.
2. Comparez la question déléguée au nom et aux arguments de `get_alerts` dans le test.
3. Imaginez une réponse incomplète : quelles informations demanderiez-vous avant de conclure ?
4. Expliquez comment un agent distant pourrait utiliser MCP pendant une tâche A2A.

## Pour aller plus loin

Étudiez les états d'une tâche A2A et la différence entre un message et un artefact.
Les tâches de ce serveur sont conservées en mémoire : un redémarrage les efface.
Pour un déploiement partagé, prévoyez la persistance et la gestion du jeton en plus de TLS.
