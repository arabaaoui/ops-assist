# Atelier 09 — MCP : exposer et consommer des outils

## Objectif

Vous allez découvrir quatre outils d’observation via MCP et les appeler sans modèle ni réseau.
Vous comparerez ensuite leur utilisation directe et leur consommation par un agent ADK.

## Notions

MCP décrit un échange entre un client et un serveur qui propose notamment des outils.
Le client découvre les noms, descriptions et schémas, puis appelle un outil avec des arguments.
Le serveur exécute la fonction et renvoie son résultat ; le modèle ne l’exécute pas lui-même.

Le transport stdio relie l’entrée et la sortie standard d’un processus enfant au client.
La sortie standard est réservée au protocole ; les diagnostics passent sur la sortie d’erreur.
Ici, le SDK MCP 2 appelle `MCPServer` la classe auparavant nommée `FastMCP`.
Le serveur réutilise les mêmes fonctions bornées que l’agent en mode direct.

## Étapes hors ligne

### 1. Exposer les outils

Depuis la racine du projet, le serveur peut être lancé par un client avec :

```bash
uv run ops-assist mcp-serve
```

Il attend des messages MCP sur son entrée standard : aucun affichage interactif n’est attendu.
Arrêtez-le avec Ctrl+C si vous l’avez lancé seul. Le rejeu est la source par défaut.

### 2. Découvrir et appeler

Ce client lance le serveur local, découvre ses outils et lit les alertes fictives :

```bash
OPS_ASSIST_SOURCE=replay OPS_ASSIST_INCIDENT=payment-latency uv run python - <<'PY'
import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'ops_assist.mcp_server'], env={
            'OPS_ASSIST_SOURCE': os.environ['OPS_ASSIST_SOURCE'],
            'OPS_ASSIST_INCIDENT': os.environ['OPS_ASSIST_INCIDENT']})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print([tool.name for tool in (await session.list_tools()).tools])
            print((await session.call_tool('get_alerts', {})).structured_content)

asyncio.run(main())
PY
```

Résultat attendu : `get_alerts`, `get_metric`, `get_logs`, `get_changes`, puis deux alertes avec `status: ok` et leur provenance de rejeu.
Le client ferme la session et le processus serveur en sortant des blocs.

### 3. Consommer depuis ADK sans modèle réel

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_mcp.py
```

Résultat attendu : les tests passent, comparent les alertes au mode direct et font tourner l’agent avec un modèle scripté.
Pour une investigation avec votre modèle configuré, choisissez `OPS_ASSIST_TOOLS=mcp` ; `inprocess` reste le défaut.
Le serveur enfant hérite de la configuration de source et reçoit l’incident sélectionné, y compris avec `--incident`.
Le rappel de mémoire reste une fonction locale ; le pré-triage utilise aussi la source dans le processus principal.
Une source Python injectée directement ne peut pas être transférée au processus MCP et est refusée dans ce mode.

## Exercices

1. Modifiez le client pour appeler `get_changes` avec `service: payment-api` et trouvez sa provenance.
2. Appelez `get_logs` avec `limit: 1` et comparez le résultat à la fonction directe de l’atelier 08.
3. Essayez un nom de métrique inconnu et expliquez la différence entre erreur de protocole et `status: error` de l’outil.
4. Identifiez les quatre outils servis et expliquez pourquoi le rappel de mémoire n’apparaît pas dans la liste MCP.

## Pour aller plus loin

Un serveur MCP tiers est du code tiers exécuté sur votre machine, pas seulement une description d’outils.
Avant de l’installer, examinez son origine et sa version, les commandes exécutées et les dépendances téléchargées.
Vérifiez ses accès au réseau, aux fichiers, aux secrets et aux cookies, puis limitez ses permissions au strict nécessaire.
Contrôlez également les outils exposés et les données qu’ils envoient ; refaites cette revue avant toute mise à jour.
