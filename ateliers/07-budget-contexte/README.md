# Atelier 07 — Le contexte comme budget

Durée : 40 à 50 minutes. Préparez les dépendances avec `uv sync` si nécessaire.
Les données et services de cet atelier sont fictifs. Les étapes ci-dessous sont hors ligne.

## Objectif

Mesurer et réduire les données présentées au modèle.

## Notions à rappeler

Le contexte comprend instructions, message, schémas et résultats des outils.
Le modèle peut moins bien exploiter une information perdue au milieu d’un grand contexte.
Sélectionner garde les éléments utiles ; résumer réduit la taille ; plafonner borne le volume.
Toute réduction peut perdre des indices : la taille seule ne garantit pas la qualité.

## Étapes

Depuis la racine du dépôt, exécutez :

```bash
uv run ops-assist tokens --incident payment-latency
uv run pytest -q tests/test_module1.py -k tools
uv run ops-assist triage
```

Résultats attendus :

- Le tableau donne une estimation locale par fichier et un total.
- Le test vérifie notamment les plafonds des journaux et le résumé de métrique.
- Le tri affiche un petit ensemble de candidats, pas tous les fichiers.

Poursuivez la lecture :

- Le tokenizer local est une approximation, différente selon les modèles réels.
- Les journaux sont limités en nombre et chaque message à 300 caractères.
- Au-delà de 60 points, une série devient statistiques et dix points autour du plus grand saut.
- La moyenne et les extrêmes ne permettent pas de reconstruire toute la série.
- Avec un modèle configuré, ajoutez `--show-context` à `investigate`.
- Le tableau estime les tokens de la requête sérialisée à chaque tour, pas le compte du fournisseur ni une facture exacte.

Pour comparer une série fictive brute à sa version plafonnée, exécutez :

```bash
uv run python -c 'import asyncio,json; from ops_assist.tools import make_tools; S=type("S",(),{"metric":lambda self,n,s:{"points":[[i,i] for i in range(1000)]}}); raw=S().metric("m","s"); capped=asyncio.run(make_tools(S())[1]("m","s")); print("brut",len(json.dumps(raw)),"plafonné",len(json.dumps(capped)))'
```

La taille affichée en caractères pour la version plafonnée doit être inférieure.
Le gain en tokens dépend du tokenizer ; une réduction peut perdre des détails utiles.

## Exercices

1. Comparez les caractères des journaux et des alertes dans `tokens`. Observez le poids relatif.

2. Lisez le test de série longue : comparez 100 points bruts aux dix conservés. Observez la perte de détail.

3. Cherchez une anomalie éloignée du plus grand saut. Observez comment le résumé peut la masquer.

4. Avec un modèle, comparez les tours affichés par `--show-context`. Observez la croissance liée aux réponses d’outils.

## Pour aller plus loin

Mesurez aussi la qualité du diagnostic après réduction, avec des incidents fictifs variés.

Vous pouvez effectuer cet atelier sans appel de modèle ni accès réseau.
Les exemples sont pédagogiques : une validation de format ne prouve pas une cause.
Comparez vos réponses avec les observations et explicitez les incertitudes.

## Bilan du module 1

Vous avez manipulé tokens, formats validés, outils et boucle agentique.
Vous savez distinguer sous-systèmes, workflow, mémoire et contexte.
Vous pouvez maintenant argumenter les limites d’une enquête automatisée.
