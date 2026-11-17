# Atelier 29 — Dans un GPU : entraînement et inférence

## Objectif

Vous mesurez la latence et le débit de génération, puis comparez deux quantifications.
Vous reliez ces mesures à la mémoire et à la qualité sur un incident fictif.
Le parcours hors ligne utilise des flux simulés, sans modèle ni téléchargement.

## Notions rappelées

Pendant l'entraînement, le modèle ajuste ses poids à partir de données et de gradients.
Pendant l'inférence, les poids restent fixes et le modèle produit une réponse.
Le **prefill** traite le prompt et prépare le contexte avant la génération.
Le **decode** génère ensuite les tokens successivement, en réutilisant le contexte.
La latence jusqu'au premier texte visible inclut le prefill et les délais de transport.
Le cache KV conserve clés et valeurs de l'attention pour éviter des recalculs.
Il consomme de la mémoire qui augmente notamment avec la longueur du contexte.
Un lot regroupe des requêtes pour mieux utiliser le matériel, au prix d'attente possible.
Le continuous batching accepte et termine des requêtes pendant l'exécution du lot.
PagedAttention gère le cache KV par blocs ; vLLM l'utilise pour réduire le gaspillage.
Kwon et al., 2023 présentent cette approche dans « Efficient Memory Management for
Large Language Model Serving with PagedAttention » : https://arxiv.org/abs/2309.06180.
La quantification représente les poids avec moins de bits pour réduire leur taille.
Elle peut modifier la qualité et la vitesse ; le matériel et le format comptent aussi.

## Étapes hors ligne

Depuis la racine du dépôt, exécutez les mesures sur des flux simulés :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_bench.py
uv run ops-assist eval list
```

Résultat attendu : les tests passent et la liste contient des incidents fictifs.
Les horloges injectées rendent les durées vérifiables sans appel réseau.
Le test vérifie la médiane, le minimum et le maximum de plusieurs générations.
Un fragment reçu peut contenir plusieurs tokens : ne comptez pas les fragments.

## Étapes avec un modèle local déjà installé

Préparez un fichier de prompt fictif, identique pour les deux essais :

```bash
printf 'Analysez une hausse fictive de latence et proposez une vérification.\n' > /tmp/ops-prompt.txt
OPS_ASSIST_MODELS=ollama_chat/example:q4_K_M uv run ops-assist bench --profile local --runs 3 --prompt-file /tmp/ops-prompt.txt --ollama
OPS_ASSIST_MODELS=ollama_chat/example:q8_0 uv run ops-assist bench --profile local --runs 3 --prompt-file /tmp/ops-prompt.txt --ollama --json
```

Remplacez `example` par deux variantes déjà présentes du même modèle.
Résultat attendu : tableau ou JSON avec médiane, minimum et maximum par mesure.
`ttft_seconds` mesure le délai jusqu'au premier fragment de texte non vide.
`decode_tokens_per_second` divise les tokens après le premier par le temps entre
premier et dernier fragments de texte ; c'est une approximation de débit observé.
Le dernier fragment peut contenir plusieurs tokens ; les tokens de raisonnement
éventuels peuvent aussi être inclus dans le total renvoyé par LiteLLM.
LiteLLM peut estimer cet usage si le fournisseur ne le donne pas.
Sans nombre de tokens disponible, ou sans intervalle mesurable, le débit est indisponible.
`total_seconds` inclut l'arrivée des métadonnées finales et la fin du flux.
`--ollama` interroge facultativement le service local sur le port 11434 pour la
mémoire du modèle chargé ; `null` indique une mesure absente ou indisponible.
Les essais sollicitent un modèle : un profil, modèle ou endpoint distant exige
`--allow-remote` et peut entraîner un coût. Aucun repli de modèle n'est effectué.

Choisissez un incident dans `eval list`, puis utilisez la même question et
`uv run ops-assist eval run --profile local --show-reports` pour chaque variante.
Examinez le rapport de cet incident et ses contrôles, avec les mêmes paramètres.
L'évaluation complète exige un modèle ; elle ne mesure pas seule la qualité globale.

| Variante | TTFT médiane | Débit médian tokens/s | Mémoire totale / GPU | Contrôle qualité sur l'incident |
|---|---:|---:|---:|---|
| q4_K_M | à mesurer | à mesurer | à mesurer | à observer |
| q8_0 | à mesurer | à mesurer | à mesurer | à observer |

## Exercices

1. Expliquez pourquoi une augmentation du prompt peut augmenter le prefill.
2. Comparez les deux lignes ; répétez les essais et discutez leur dispersion.
3. Expliquez pourquoi le cache KV peut limiter la taille d'un lot.
4. Avec les tests simulés, supprimez le comptage fourni et observez le débit absent.

## Pour aller plus loin

Comparez les résultats à longueur de prompt et limites de génération constantes.
Étudiez PagedAttention et le continuous batching avec l'article de Kwon et al.
Hors ligne, relisez les tests et dessinez l'évolution du cache pendant le decode.

Le fichier de prompt est limité à 64 Kio avant décodage. L’endpoint effectif provient de la configuration, puis de `OLLAMA_API_BASE`, puis de `http://localhost:11434` ; une adresse hors boucle locale exige `--allow-remote`.
