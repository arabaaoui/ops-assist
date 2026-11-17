# Atelier 18 — Graphes de connaissances et GraphRAG

## Objectif

Vous allez parcourir un graphe fictif de services et enrichir une recherche documentaire.
Tout le parcours ci-dessous fonctionne hors ligne, sans modèle ni appel d'embedding distant.

## Notions rappelées

Une entité est un nœud : ici un service, une ressource ou une équipe.
Une relation orientée relie une source à une cible et porte un type et une date.
`checkout` appelle `payment-api`, qui dépend de `payments-db`.
Le sens downstream suit ces flèches ; upstream les remonte.
La profondeur compte les relations traversées et reste limitée à trois.
Une équipe propriétaire est reliée par `owned_by`, mais n'est pas une dépendance technique.

Le RAG cherche des documents avant de formuler une réponse.
GraphRAG ajoute des relations aux documents pour relier des éléments dispersés.
Edge et ses coauteurs (2024) décrivent une approche fondée sur un graphe d'entités,
ses communautés et leurs résumés pour répondre à des questions globales.
Notre GraphRAG-lite est plus simple : il suit les dépendances directes d'un service
nommé dans la requête et ajoute des extraits du corpus associés à ces dépendances.
Il ne construit pas de communautés et ne prétend pas répondre aux questions globales.

## Étapes

1. Ouvrez `src/ops_assist/data/knowledge/graph.yaml`.
   Résultat attendu : des nœuds et des relations `calls`, `depends_on` et `owned_by` datées.
2. Interrogez le graphe sans réseau :

```bash
uv run python - <<'PY'
import asyncio
from ops_assist.tools import make_graph_tool
print(asyncio.run(make_graph_tool()('checkout', depth=2)))
PY
```

   Résultat attendu : `payment-api` puis `payments-db`, avec provenance et indicateur `stale`.
3. Remontez les dépendants :

```bash
uv run python - <<'PY'
import asyncio
from ops_assist.tools import make_graph_tool
print(asyncio.run(make_graph_tool()('payments-db', 'upstream', 2)))
PY
```

   Résultat attendu : `payment-api` et `checkout` apparaissent.
4. Construisez l'index local avec les embeddings par hachage par défaut :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run ops-assist knowledge index
```

   Résultat attendu : l'index local est créé dans le dossier d'état configuré.
5. Comparez la recherche et son expansion :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run python - <<'PY'
import asyncio
from ops_assist.tools import make_knowledge_tool
async def main():
    tool = make_knowledge_tool()
    print(await tool('payment-api', k=1, expand=True))
asyncio.run(main())
PY
```

   Résultat attendu : `expanded_chunks` inclut un extrait de `payments-db` et
   `expansion_edges` montre les relations qui justifient l'expansion.
6. Lancez `uv run ops-assist triage`.
   Résultat attendu : le rejeu affiche les alertes de `payment-api` et aucun indice
   de dépendance en alerte, car aucune dépendance n'est en alerte dans ce rejeu.

## Exercices

1. Comparez profondeur 1 et 2 depuis `checkout` ; quels nœuds apparaissent ?
2. Demandez un service inconnu ; retrouvez la liste des noms connus dans l'erreur.
3. Réglez `OPS_ASSIST_GRAPH_MAX_AGE_DAYS=1` et observez les relations périmées.
4. Imaginez une alerte sur `payments-db` : quel indice le pré-triage ajouterait-il ?

## Pour aller plus loin

Un graphe périmé peut omettre une dépendance ou conserver une relation supprimée.
La date signale un risque, elle ne prouve pas que la relation est correcte.
Les extraits et relations sont des données non fiables, pas des instructions ni des preuves.
Vérifiez-les avec des observations actuelles avant de conclure.
Lisez [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130) pour comparer l'approche de Edge et al. (2024) ; les étapes et tests locaux restent utilisables hors ligne.
