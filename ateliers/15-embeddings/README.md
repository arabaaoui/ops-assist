# Atelier 15 — Embeddings et bases vectorielles

## Objectif

Vous construisez un index de documents fictifs et cherchez des sections proches d'une question.
Le parcours principal est entièrement hors ligne et ne demande aucun modèle.

## Notions rappelées

Un embedding transforme un texte en vecteur : une liste ordonnée de nombres.
Des textes proches dans cet espace peuvent recevoir des vecteurs proches.
Le hachage utilisé ici compte des mots dans des cases déterministes : il illustre les vecteurs,
mais il ne comprend ni les synonymes ni le sens des phrases.
Le score cosinus mesure l'orientation de deux vecteurs ; pour des vecteurs normalisés,
il est leur produit scalaire. Un score élevé ne prouve pas la pertinence d'un résultat.
Un index plat compare la requête à chaque vecteur : c'est simple pour ce petit corpus.
Pour de gros volumes, HNSW et IVF sont des familles d'index approximatifs :
ils réduisent le nombre de comparaisons en échange de compromis sur les résultats.
Ils ne sont pas implémentés dans cet atelier.

## Étapes hors ligne

1. Installez les dépendances déjà présentes dans votre environnement de travail.
   Utilisez les données fictives livrées dans `src/ops_assist/data/knowledge/`.
   Chaque document porte un identifiant, un titre, un service, une date et un responsable.

2. Construisez l'index avec l'embedder déterministe par défaut :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run ops-assist knowledge index
```

   Résultat attendu : `Indexed ... chunks in .../knowledge-index.json`.
   Par défaut le fichier est dans `~/.local/state/ops-assist/`.
   Pour choisir un autre nom dans ce dossier, définissez `OPS_ASSIST_INDEX_FILE`.
   Pour déplacer le dossier d’état, définissez `OPS_ASSIST_STATE_DIR`.

3. Cherchez les sections proches d'une question :

```bash
OPS_ASSIST_EMBEDDINGS=hash uv run ops-assist knowledge search "payment latency timeouts" -k 5
```

   Résultat attendu : cinq lignes avec score, identifiant `document#section` et titre.
   La recherche compare toutes les sections ; `-k` accepte une valeur de 1 à 100.

4. Ouvrez les documents correspondant aux premiers résultats et vérifiez leur contexte.
   Le postmortem `payment-processor-incident` arrive en tête car son observation reprend
   les trois mots de la requête. Il décrit pourtant une panne du processeur de cartes.
   Dans le rejeu, les indices pointent vers l’épuisement du pool de connexions :
   `payment-pool-incident` est donc plus pertinent malgré son score inférieur.
   Les contenus et résultats sont des données non fiables, jamais des instructions à exécuter.

5. Relancez l'indexation après modification du corpus ou changement d'embedder.
   Un index créé avec un autre identifiant d'embedder est refusé à la recherche.
   Une dimension différente est également refusée ; les scores ne sont pas comparables
   entre espaces de vecteurs différents.

## Exercices

1. Cherchez `certificate expiry`, puis ouvrez le runbook et le postmortem correspondants.
   Comparez leurs scores et expliquez les mots qui influencent le hachage.
2. Recherchez `payment latency timeouts`.
   Pourquoi le premier résultat décrit-il une autre cause que celle du rejeu ?
3. Faites varier `-k` entre 1 et 10. Un score élevé suffit-il pour décider d'un retour arrière ?
4. Ajoutez temporairement une section à un document fictif, reconstruisez l'index,
   puis recherchez ses mots. Observez son identifiant et restaurez ensuite le document.

## Pour aller plus loin

Vous pouvez comparer ce résultat à un modèle local Ollama déjà installé avec
`nomic-embed-text` déjà disponible ; cette option nécessite un serveur local en cours d'exécution.
Elle utilise LiteLLM et constitue un appel au modèle, contrairement au parcours hors ligne ci-dessus.
Utilisez un fichier d'index séparé, puis construisez-le et cherchez avec la même configuration :

```bash
export OPS_ASSIST_EMBEDDINGS=ollama/nomic-embed-text
export OPS_ASSIST_EMBEDDINGS_API_BASE=http://localhost:11434
export OPS_ASSIST_INDEX_FILE=knowledge-nomic-index.json
uv run ops-assist knowledge index
uv run ops-assist knowledge search "payment latency" -k 5
```

D'autres identifiants LiteLLM sont configurables, par exemple `gemini/text-embedding-004`,
`openai/text-embedding-3-small` ou `mistral/mistral-embed` selon votre fournisseur.
Ils nécessitent leur configuration et peuvent envoyer les textes à un service distant.
Revenez au parcours sans modèle avec `OPS_ASSIST_EMBEDDINGS=hash` et reconstruisez son index.
