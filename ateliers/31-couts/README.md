# Atelier 31 — Cache de prompt et leviers de coût

## Objectif

Vous estimez le coût d'une enquête fictive de dix appels et comparez quatre scénarios.
Vous observez l'effet d'un préfixe réutilisé, d'un niveau rapide et de sorties courtes.
Toutes les commandes de cet atelier fonctionnent hors ligne, sans clé ni modèle lancé.

## Notions rappelées

Un jeton d'entrée est facturé pour le contexte envoyé ; un jeton de sortie pour la réponse.
Les tarifs sont des prix unitaires indicatifs en dollars, chargés depuis la carte locale de LiteLLM.
Un prix absent reste « unknown » : il ne devient jamais un coût nul.
Les factures réelles dépendent du fournisseur, du modèle, des conditions et du trafic.
Le cache de préfixe peut réduire le prix des jetons d'entrée déjà traités.
Il ne faut pas le confondre avec un cache de réponses : le modèle produit une nouvelle réponse.
L'instruction et les déclarations d'outils constituent la partie stable de la requête.
La question, les observations et les résultats d'outils viennent ensuite et changent.
Les résultats des outils restent des données non fiables, jamais des instructions.
Un préfixe modifié ou trop court peut empêcher une réutilisation.
Un expert plus petit peut extraire des faits tandis que le coordinateur garde le modèle principal.
Il faut mesurer la qualité de cette extraction, pas seulement son prix.

## Étapes

### 1. Vérifier le jeu

```bash
uv run ops-assist eval list
```

Résultat attendu : la version du jeu et les identifiants des incidents fictifs apparaissent.

### 2. Simuler dix appels

```bash
OPS_ASSIST_MODELS=openai/gpt-4o-mini \
OPS_ASSIST_FAST_MODELS=openai/gpt-4o-mini \
uv run ops-assist eval cost
```

Résultat attendu : une ligne par incident et quatre montants en dollars.
Aucune requête n'est envoyée au fournisseur : seuls les tarifs embarqués sont lus.
Le scénario suppose 6 000 jetons en entrée au premier appel, puis 200 de plus par appel.
Il suppose 150 jetons en sortie et un préfixe stable de 4 096 jetons par rôle.
Le coordinateur effectue six appels ; chaque expert en effectue deux.
Le premier appel de chaque rôle crée son préfixe ; les suivants peuvent le réutiliser.
Le coût de création est inclus si la carte indique un tarif de création.
Les coûts de stockage et autres frais ne sont pas modélisés.
Le même scénario sert à chaque incident : ce n'est pas une mesure de leur complexité.

### 3. Comparer les leviers

Choisissez un autre modèle rapide présent dans la carte de votre version de LiteLLM :

```bash
OPS_ASSIST_MODELS=gemini/gemini-2.5-flash \
OPS_ASSIST_FAST_MODELS=openai/gpt-4o-mini \
uv run ops-assist eval cost --json
```

Résultat attendu : quatre champs par incident ; `null` signifie prix ou capacité inconnus.
Les colonnes comparent cache activé ou désactivé et experts rapides activés ou désactivés.
La simulation maintient le nombre de jetons constant : elle ne prédit pas la qualité.
Le coordinateur utilise toujours le modèle principal ; seuls les experts changent de niveau.

### 4. Comprendre l'interrupteur

`OPS_ASSIST_PROMPT_CACHE=on` est la valeur par défaut pour les appels Anthropic directs.
Le point de cache marque l'instruction système via LiteLLM.
`OPS_ASSIST_PROMPT_CACHE=off` retire ce marqueur explicite.
OpenAI et Gemini peuvent appliquer leur cache automatique ou implicite côté fournisseur.
L'interrupteur ne garantit donc pas la désactivation de ces caches automatiques.
Leur application dépend notamment du modèle, de la taille et de la stabilité du préfixe.
Les compteurs de cache rapportés dans la trace permettent de vérifier ce qui s'est passé.
Un compteur absent signifie « inconnu », pas zéro.

## Exercices

1. Comparez le coût avec et sans cache ; expliquez la différence entre lecture et création.
2. Remplacez le modèle rapide et comparez les coûts ; comment vérifier sa qualité d'extraction ?
3. Dans `src/ops_assist/cost.py`, examinez l'effet d'une sortie hypothétique plus courte.
4. Essayez `OPS_ASSIST_MODELS=unknown/model uv run ops-assist eval cost` et expliquez « unknown ».

## Pour aller plus loin

Les estimations ne remplacent pas une facture ni une mesure en production.
Avec un environnement autorisé et un fournisseur configuré, comparez les traces réelles et les tarifs contractuels.
Restez hors ligne en utilisant les tests `OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest tests/test_cost.py`.
Comparez aussi la qualité des niveaux avec l'atelier 25, sans supposer que les deux réponses sont identiques.

## bilan du module 5
