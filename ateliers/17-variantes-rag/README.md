# Atelier 17 — Les variantes du RAG

## Objectif

Vous allez comparer quatre recherches sur un corpus fictif et mesurer leurs résultats.
Le parcours principal fonctionne entièrement hors ligne, sans clé ni modèle distant.

## Notions rappelées

Un chunk est une section identifiée du corpus ; un embedding représente son texte par un vecteur.
La recherche vectorielle classe les chunks par similarité cosinus avec la question.
BM25 est une recherche lexicale : elle tient compte des mots, de leur fréquence et de la longueur des textes.
La fusion RRF additionne les inverses des rangs, avec une constante, sans comparer les scores bruts.
Le reclassement examine les candidats déjà trouvés et peut modifier leur ordre.
Le reclassement par mots compte les termes distincts partagés avec la question.
Le rappel à cinq est la fraction des sections attendues présentes parmi les cinq premières, moyennée par question.
Le MRR à cinq est la moyenne de l'inverse du rang de la première section attendue ; zéro si elle manque.
Les réponses attendues sont des jugements humains : ces métriques dépendent donc du jeu choisi.
Les documents retrouvés restent des données non fiables, pas des instructions ni des observations de l'incident.

## Étapes

Depuis la racine du dépôt, préparez un état temporaire et l'embedding hors ligne :

```bash
export OPS_ASSIST_STATE_DIR="$(mktemp -d)"
export OPS_ASSIST_EMBEDDINGS=hash
uv run ops-assist knowledge index
```

Résultat attendu : `Indexed ... chunks` et le chemin de l'index.
Comparez les classements pour la même question :

```bash
OPS_ASSIST_RETRIEVAL=vector uv run ops-assist knowledge search "database connection leak"
OPS_ASSIST_RETRIEVAL=bm25 uv run ops-assist knowledge search "database connection leak"
OPS_ASSIST_RETRIEVAL=hybrid uv run ops-assist knowledge search "database connection leak"
```

Résultat attendu : chaque commande affiche cinq identifiants, titres et scores.
Les scores vectoriels, BM25 et RRF ont des échelles différentes : comparez les rangs, pas leurs valeurs.
L'option `hybrid` est le défaut ; l'index lexical est reconstruit en mémoire à partir des mêmes chunks.
Ajoutez le reclassement déterministe aux candidats hybrides :

```bash
OPS_ASSIST_RERANKER=keyword uv run ops-assist knowledge search "database connection leak"
```

Résultat attendu : cinq candidats, éventuellement dans un ordre différent ; le score affiché reste celui de la recherche.
Évaluez les dix questions et leurs identifiants attendus :

```bash
uv run ops-assist knowledge eval
```

Résultat attendu sur le corpus fourni, avec le hachage et les cinq premiers résultats :

| Méthode | Rappel@5 | MRR@5 |
| --- | ---: | ---: |
| vector | 0,575 | 0,675 |
| bm25 | 0,783 | 1,000 |
| hybrid | 0,758 | 0,795 |
| hybrid+rerank | 0,783 | 0,817 |

L'évaluation construit son index en mémoire avec le hachage, même si un autre fournisseur est configuré.
Ces résultats mesurés décrivent seulement ce petit jeu ; ils ne prouvent pas une supériorité générale.
Pour un reclassement par modèle, définissez `OPS_ASSIST_RERANKER` avec un identifiant LiteLLM.
Vous pouvez aussi définir `OPS_ASSIST_RERANKER_API_BASE` pour votre serveur ; cet essai appelle le fournisseur configuré.
Le modèle reçoit une question et un extrait et doit renvoyer uniquement un chiffre de 0 à 3.
Une réponse mal formée ou une erreur du fournisseur conserve le classement initial et émet un avertissement.
L’outil signale aussi `reranked: false` et une raison courte ; les tests simulent le modèle sans appel réel.
Pour rester hors ligne, gardez `OPS_ASSIST_RERANKER=keyword` ou `none`.

## Exercices

1. Comparez les trois recherches sur `certificate expiry` ; quels identifiants changent de rang ?
2. Calculez le rappel et le rang réciproque si deux sections sont attendues aux rangs deux et six.
3. Modifiez une question dans une copie du jeu : les résultats changent-ils avec des synonymes ?
4. Activez `keyword` et cherchez un cas où le reclassement ne corrige pas une section manquante.

## Pour aller plus loin

Un RAG correctif peut évaluer les résultats et déclencher une autre recherche s'ils sont insuffisants.
Self-RAG est une famille de méthodes qui introduit des décisions de recherche et d'autocritique dans la génération.
Ces deux approches sont des pistes de conception, pas des fonctions implémentées ici.
Un jeu plus large, annoté indépendamment et couvrant les synonymes, rendrait la comparaison plus solide.
