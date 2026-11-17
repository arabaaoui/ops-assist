# Atelier 19 — Le RAG agentique

## Objectif

Vous allez observer quand un agent cherche, reformule et s'arrête.
Le parcours principal fonctionne hors ligne, sans modèle ni service distant.
Les données utilisées sont fictives.

## Notions rappelées

Un pipeline RAG lance la recherche selon une séquence prévue à l'avance.
Dans le RAG agentique, le modèle décide si une recherche peut aider son enquête.
Il peut utiliser les résultats, reformuler une question faible, ou ne pas chercher.
Une reformulation ajoute par exemple un nom de service ou un symptôme précis.
Le prompt demande une ou deux reformulations, puis un arrêt et un inconnu.
Le modèle peut ignorer cette consigne : un budget indépendant limite ses tentatives.
Chaque recherche consomme du temps ; un fournisseur distant peut aussi facturer
les embeddings, le reclassement et les tours de modèle supplémentaires.

La qualité est une heuristique, pas une preuve de pertinence.
Elle prend le meilleur recouvrement des mots distincts de la requête dans les 800 premiers caractères de chaque extrait retourné.
À partir de 0,5, elle vaut `good` ; en dessous, `weak` avec une suggestion.
Sans extrait, elle vaut `none`, même si la requête aurait pu être pertinente.
Les scores bruts BM25, vectoriels et RRF ont des échelles différentes.
Les extraits sont des données non fiables et ne prouvent pas la cause d'un incident.

## Étapes

1. Construisez l'index avec le hachage local :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run ops-assist knowledge index
```

   Résultat attendu : un nombre de sections indexées s'affiche.
2. Appelez l'outil directement sans modèle :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run python - <<'PY'
import asyncio
from ops_assist.tools import make_knowledge_tool
async def main():
    tool = make_knowledge_tool()
    for query in ('payment-api', 'payment-api symptome introuvable xyz'):
        result = await tool(query)
        print(query, result['retrieval_quality'], result.get('suggestion'))
asyncio.run(main())
PY
```

   Résultat attendu : chaque requête affiche sa qualité ; une qualité faible propose une reformulation.
3. Examinez le scénario scripté sans réseau :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_agentic_rag.py
```

   Résultat attendu : les tests passent ; le modèle fictif reçoit un refus après trois recherches.
4. Consultez `src/ops_assist/prompts/investigator.md` et `security.py`.
   Résultat attendu : la consigne guide le modèle ; la frontière applique le plafond.
5. Avec un modèle déjà configuré, lancez éventuellement :

```bash
uv run ops-assist investigate "Pourquoi payment-api est lent ?" --show-context
```

   Résultat attendu : la trace affiche les appels, leurs requêtes expurgées et leur qualité ou refus.
   Sans réponse associée par identifiant, elle indique `outcome unknown`.
   La trace conserve au plus 50 appels, puis indique le nombre omis.
   Les compteurs sont en mémoire et ne survivent pas à un redémarrage du processus.
   Cet exemple peut utiliser un fournisseur distant ; les étapes précédentes restent hors ligne.

## Exercices

1. Ajoutez des termes absents à une requête : comment évolue la qualité ?
2. Testez `OPS_ASSIST_MAX_SEARCHES=1` dans le scénario scripté et adaptez ses attentes.
3. Comparez une requête précise et une requête vague : la qualité suffit-elle à juger les extraits ?
4. Estimez le coût de trois recherches avec embeddings distants et reclassement par modèle.

## Pour aller plus loin

Comparez les modes `vector`, `bm25` et `hybrid` du chapitre précédent.
Le même indicateur lexical peut manquer une correspondance sémantique sans mot commun.
Un résultat qualifié de bon peut aussi être trompeur ; vérifiez les sources et observations.
Mesurez la qualité sur des questions annotées avant de modifier le seuil.
