# Atelier 13 — La sécurité d'un agent

## Objectif

Vous protégez les outils d'un agent d'enquête, puis vous examinez une tentative d'injection.
Vous vérifiez les décisions et leur journal sans réseau ni modèle réel.

## Notions

Un callback ADK intervient avant ou après un appel d'outil.
Il constitue ici la frontière entre une proposition du modèle et son exécution.
Un résultat non nul du callback avant appel refuse l'exécution et fournit une réponse structurée.
Le même contrôle s'applique au coordinateur, aux experts et aux outils MCP appelés par ADK.
Les outils de lecture consultent des données ; l'écriture modifie un état.
Un nom inconnu est considéré comme une écriture et refusé.
La table explicite est `TOOL_ACCESS` dans `src/ops_assist/security.py`.
La délégation est comptée séparément, tout en comptant comme appel d'outil.
Les plafonds sont calculés par invocation ADK, partagés entre coordinateur et experts.
La reprise après confirmation garde le même compteur en mémoire ; ce compteur ne persiste pas.

La lecture seule est le défaut ; l'outil de retour arrière n'est alors pas exposé.
`OPS_ASSIST_ALLOW_WRITES=1` expose l'outil, sans supprimer la confirmation humaine.
ADK 2.14.1 suspend l'appel et transmet une demande de confirmation au client.
La CLI demande de saisir exactement `yes` ; tout autre texte refuse.
L'interface ADK web permet aussi de confirmer ou rejeter la demande.
Les serveurs A2A et MCP n’exposent jamais d’écriture.
Un agent peut consulter des outils MCP et proposer un retour arrière confirmé dans la CLI ou ADK web.
Un message A2A ne vaut pas confirmation humaine.
Une confirmation ne rend pas un connecteur réel modifiable : son retour arrière est toujours refusé.
En rejeu, seule une copie d'état simulé est modifiée, jamais les données enregistrées.
La démonstration nécessite un client explicitement injecté et reste indisponible hors ligne sans lui.

L'audit JSONL contient le nom, les arguments expurgés, le résultat et la durée de chaque appel.
Les résultats sont `ok`, `failed` et `denied`, confirmation manquante comprise.
Une entrée `pending` synchronisée précède toute écriture confirmée ; si elle échoue, rien ne change.
L'expurgation utilise les mêmes règles heuristiques que la mémoire ; elle n'est pas une garantie.
Utilisez des données fictives et protégez les fichiers d'audit et de session.
Les appels dépassant une limite ou refusés restent visibles dans l'audit.

## Étapes hors ligne

### 1. Vérifier l'injection

```bash
rg 'IGNORE ALL PREVIOUS' src/ops_assist/data/incidents/payment-latency/logs.jsonl
```

Résultat attendu : une ligne demande de revenir en arrière sur tous les services.
Cette ligne est une donnée non fiable, pas une autorisation humaine.

### 2. Exécuter les scénarios de sécurité

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_security.py
```

Résultat attendu : les scénarios passent sans connexion ni modèle.
Le modèle scripté lit le journal piégé, puis propose un retour arrière.
Sans confirmation, ADK suspend l'outil, l'audit indique `denied` et l'état reste intact.
Après confirmation, le rejeu passe de `v2.14` à `v2.13` dans un fichier temporaire.
Un refus humain ne modifie rien ; un connecteur réel refuse même après confirmation.
Le client de démonstration est remplacé par un objet fictif qui vérifie les arguments.

### 3. Examiner les limites et l'audit

```bash
rg -n 'TOOL_ACCESS|DELEGATIONS|OPS_ASSIST_MAX|audit_path' src/ops_assist/security.py
```

Résultat attendu : les deux plafonds et les catégories sont visibles.
`OPS_ASSIST_MAX_TOOL_CALLS` vaut 100 par défaut et `OPS_ASSIST_MAX_DELEGATIONS` vaut 10.
Les valeurs doivent être des entiers strictement positifs.
Configurez `OPS_ASSIST_STATE_DIR` pour choisir la racine privée des fichiers locaux.
`OPS_ASSIST_AUDIT_FILE` accepte un simple nom de fichier dans cette racine, jamais un chemin.
Par défaut ils sont dans `~/.local/state/ops-assist/`.
Les tests utilisent des répertoires temporaires et ne modifient pas les enregistrements livrés.

### 4. Essai interactif facultatif

Avec un modèle local déjà configuré, lancez :

```bash
OPS_ASSIST_ALLOW_WRITES=1 uv run ops-assist investigate "Enquêtez sur payment-api"
```

Résultat attendu : si le modèle propose un retour arrière, la CLI affiche le service et le déploiement et attend votre réponse.
L'outil peut ne pas être proposé : la décision du modèle n'est pas déterministe.
Pour un parcours entièrement hors ligne sans modèle, utilisez les tests de l'étape 2.

## Exercices

1. Fixez la limite d'appels à 1 dans un test et vérifiez le refus du deuxième appel.
2. Vérifiez qu'un nom d'outil inconnu est classé en écriture même si son nom commence par `get_`.
3. Ajoutez un argument fictif contenant `password=...` et vérifiez son expurgation dans l'audit.
4. Refusez la confirmation et comparez l'état simulé avant et après.

## Pour aller plus loin

Comparez le contrôle d'une proposition d'outil avec une règle écrite dans le prompt.
Étudiez les limites d'une expurgation heuristique et d'un audit stocké localement.
Une interface distante doit authentifier la personne qui confirme et protéger sa session.
