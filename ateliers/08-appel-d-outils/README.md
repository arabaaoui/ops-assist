# Atelier 08 — L’appel d’outils

## Objectif

Vous allez observer comment une fonction Python devient un outil ADK et comment son résultat revient au modèle. Le parcours principal utilise le rejeu et fonctionne sans réseau ni modèle.

## Notions

Un outil expose une opération précise avec des paramètres typés et une description. ADK transforme sa signature et sa docstring en déclaration destinée au modèle.

Le cycle est : schéma → choix et appel par le modèle → exécution par ADK → résultat transmis au modèle. Le modèle ne lance pas lui-même le code Python. Les observations sont des données, pas des instructions à suivre.

Une interface utile a un nom explicite, peu de paramètres, des erreurs compréhensibles et des résultats bornés avec leur provenance. Ici, `get_logs` limite les lignes et signale les erreurs par `status`.

Les outils sont asynchrones : leurs opérations bloquantes utilisent un pool dédié limité à quatre threads et quatre tâches en attente. `OPS_ASSIST_TOOL_TIMEOUT` limite l’attente à 10 secondes par défaut. Un thread bloqué est abandonné après expiration et peut continuer jusqu’à la sortie du processus ; il ne retarde pas son arrêt. Si le pool est saturé, l’outil renvoie une erreur.

## Étapes hors ligne

### 1. Examiner la déclaration

Depuis la racine du projet, lancez :

```bash
uv run python - <<'PY'
from google.adk.tools.function_tool import FunctionTool
from ops_assist.observability import ReplaySource
from ops_assist.tools import make_tools

get_logs = make_tools(ReplaySource('payment-latency'))[2]
declaration = FunctionTool(get_logs)._get_declaration()
print(declaration.model_dump_json(indent=2, exclude_none=True))
PY
```

Résultat attendu : une déclaration nommée `get_logs`, avec la description issue de sa docstring et les paramètres `service`, `level` et `limit`. La méthode `_get_declaration` est interne à cette version d’ADK : elle sert ici à inspecter le schéma.

### 2. Exécuter un outil sans modèle

```bash
uv run python - <<'PY'
import asyncio
from ops_assist.observability import ReplaySource
from ops_assist.tools import make_tools

async def main():
    tool = make_tools(ReplaySource('payment-latency'))[2]
    print(await tool('payment-api', level='error', limit=1))

asyncio.run(main())
PY
```

Résultat attendu : `status: ok`, au plus une ligne et une provenance `replay:.../logs`. Essayez un niveau inconnu : vous obtenez `status: error` et une explication.

### 3. Observer le délai

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_live_sources.py -k timeout
```

Résultat attendu : le test passe ; une source lente expire sans immobiliser la boucle asynchrone. Un délai HTTP distinct borne également les appels aux connecteurs.

## Exercices

1. Affichez la déclaration de `get_metric` et repérez ses paramètres obligatoires.
2. Appelez `get_logs` avec `limit=0` et expliquez pourquoi une erreur aide davantage le modèle qu’une liste vide.
3. Diminuez le délai du test de source lente, puis vérifiez que la boucle progresse toujours.
4. Comparez la provenance des alertes et des changements dans les enregistrements de rejeu.

## Pour aller plus loin

Les tests `tests/test_live_sources.py` utilisent avec `httpx.MockTransport` des fixtures fabriquées à la main au format des API Prometheus et Loki, sans serveur. Elles ne sont pas capturées depuis un serveur réel et ne vérifient pas la fenêtre temporelle. Vous pouvez les modifier pour étudier les erreurs.

Facultatif, sur vos propres services accessibles et autorisés : définissez `OPS_ASSIST_SOURCE=live`, `OPS_ASSIST_PROMETHEUS_URL` et `OPS_ASSIST_LOKI_URL`, puis lancez une investigation avec un profil de modèle configuré. `OPS_ASSIST_HTTP_TIMEOUT` règle le délai HTTP en secondes. Les métriques et alertes viennent de Prometheus et les journaux de Loki. Pour les changements, définissez `OPS_ASSIST_CHANGES_FILE` vers votre fichier JSON au format de `changes.json` ; sans ce fichier, l’outil renvoie une erreur explicite. Les deux connecteurs refusent directement `changes()`.

Les recherches couvrent la dernière heure. Elles supposent un label indexé `service` et, pour Loki, un label indexé `level` avec les valeurs `debug`, `info`, `warn` ou `error`. Le filtre de niveau est envoyé à Loki avant la limite de résultats : les niveaux présents uniquement dans le contenu des lignes ne suffisent pas. Loki interroge les valeurs du label `service` pour distinguer un service connu et silencieux d’un service inconnu. Une série Prometheus ambiguë est refusée.
