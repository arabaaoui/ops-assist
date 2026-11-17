# Atelier 23 — Changer un modèle

## Objectif

Vous comparez des profils sur le même jeu d’incidents fictifs.
Vous interprétez le taux de réussite avant de choisir un modèle.

## Notions rappelées

Un profil choisit des modèles et un fournisseur via LiteLLM.
Le routage et le repli restent configurables dans les profils.
Un jeu d’évaluation sépare les observations des corrigés.
Chaque enquête part d’une nouvelle session et utilise le replay.
Le taux est le nombre de réussites divisé par le nombre d’exécutions.
Une erreur d’enquête compte comme un échec.
Le score exige un rapport valide et le statut attendu.
Pour une cause établie, l’hypothèse de confiance maximale doit citer
le service et le changement attendus dans une phrase affirmative.
Pour des hypothèses seules, une hypothèse doit citer les deux identifiants
d’une entrée acceptée, dans une même phrase affirmative.
Si les données sont insuffisantes, indiquez au moins une inconnue ;
aucune hypothèse ne doit dépasser une confiance de 0,5.
Il vérifie les catégories de sources citées dans les faits.
Il cherche les conclusions interdites par phrase, sans tenir compte de la casse
et avec quelques flexions simples, dans le résumé et les hypothèses.
Une phrase avec « not », « no », « ruled out », « excluded », « unlikely »,
« rather than » ou « instead of » est considérée comme négative.
Ce repérage prudent ne comprend pas la portée de la négation,
les doubles négations, synonymes, paraphrases ou relations causales.
Une source citée peut être inventée : relisez les rapports.
Le score ne remplace donc pas une revue humaine.
Les hypothèses acceptées du corrigé ne sont pas évaluées sémantiquement.
La mémoire existante et les réglages RAG peuvent influencer l’enquête.
Utilisez les mêmes réglages pour comparer les profils.

## Étapes et résultats attendus

1. Listez le jeu sans modèle ni réseau :

   ```bash
   uv run ops-assist eval list
   ```

   Résultat attendu : la version et six incidents fictifs.

2. Consultez les profils disponibles :

   ```bash
   uv run ops-assist profile --list
   ```

   Résultat attendu : les profils et leurs variables requises.

3. Configurez un fournisseur et son modèle selon votre environnement.
   Lancez l’évaluation avec le profil choisi :

   ```bash
   uv run ops-assist eval run --profile local --repeat 2 --show-reports
   ```

   Résultat attendu : une ligne par incident et répétition,
   les critères, rapports, erreurs, taux de réussite et chemin du JSON.
   Les rapports et erreurs enregistrés sont expurgés par heuristique :
   cette expurgation ne garantit pas l’absence de données sensibles.
   Le modèle local doit déjà être disponible ; sinon choisissez un profil configuré.

4. Comparez un autre profil avec les mêmes données et réglages.
   Les résultats sont enregistrés dans `OPS_ASSIST_STATE_DIR`.
   Ne comparez les taux que pour une même version du jeu.

## Parcours hors ligne

Sans service de modèle, exécutez les tests avec des modèles scriptés :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_evaluation.py
```

Résultat attendu : les cas du modèle correct et du modèle incorrect passent.
Les tests ne chargent aucun modèle et ne font aucun appel réseau.

## Exercices

1. Expliquez pourquoi une erreur d’enquête doit compter dans le taux.
2. Repérez une phrase interdite et proposez une paraphrase que le score manque.
3. Comparez deux profils et expliquez une différence entre leurs résultats.
4. Vérifiez pourquoi une source citée ne prouve pas que le fait est exact.

## Pour aller plus loin

Lisez la décision [sans fine-tuning](../../docs/decisions/0002-no-fine-tuning.md).
Fixez un seuil avant une comparaison, puis mesurez avec `eval run`.
Explorez les erreurs une à une avant de modifier le prompt ou le modèle.
