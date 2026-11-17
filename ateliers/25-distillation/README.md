# Atelier 25 — La distillation

## Objectif

Vous comparez deux chaînes de modèles pour les experts d'une enquête fictive.
Vous gardez le même coordinateur et mesurez le compromis qualité, jetons et durée.
Cet atelier ne réalise aucun entraînement ni transfert automatique de connaissances.

## Notions rappelées

La distillation entraîne un modèle élève à partir des réponses d'un modèle enseignant.
L'enseignant produit des exemples ou des distributions utiles à l'apprentissage.
L'élève tente de reproduire ces résultats avec moins de ressources à l'exécution.
Une simple configuration d'un modèle plus petit ne constitue pas une distillation.
Elle permet cependant de mesurer si un élève existant suffit pour une tâche donnée.
Un expert chargé de collecter des faits peut nécessiter moins de capacité que le coordinateur.
Il doit néanmoins utiliser les outils correctement et rapporter ses sources sans inventer.
Une baisse de qualité peut porter sur les cas rares ou sur l'abstention, pas seulement la moyenne.
Les jetons ne sont pas directement comparables en coût entre fournisseurs ou modèles.
La durée dépend aussi de la machine, de la charge et du nombre d'appels effectués.

Vérifiez les conditions du fournisseur de l'enseignant avant d'entraîner sur ses sorties.
Vérifiez également les licences des modèles, des données et les droits de redistribution.
Ces conditions varient : ne supposez pas que toute sortie est utilisable pour l'entraînement.
Ne transmettez que des données autorisées ; les exemples du projet sont fictifs.

## Étapes et résultats attendus

1. Affichez la configuration disponible, sans appel de modèle :

   ```sh
   uv run ops-assist profile
   ```

   Résultat attendu : `models` et `fast_models` sont identiques par défaut.
   Le profil peut définir `fast_models` ; la variable `OPS_ASSIST_FAST_MODELS` le remplace.
   Si vous remplacez `OPS_ASSIST_MODELS`, le niveau rapide suit ce remplacement par défaut.

2. Parcours entièrement hors ligne avec les modèles simulés des tests :

   ```sh
   OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_distillation.py
   ```

   Résultat attendu : les tests passent sans fournisseur ni modèle réel.
   Ils vérifient la comparaison, le routage et le comptage avec ou sans métadonnées.

3. Pour mesurer vos propres modèles disponibles, configurez leurs identifiants LiteLLM :

   ```sh
   export OPS_ASSIST_MODELS='provider/main-model'
   export OPS_ASSIST_FAST_MODELS='provider/small-model'
   uv run ops-assist eval run --compare-tiers --repeat 2
   ```

   Remplacez ces identifiants fictifs par ceux de votre installation et configurez son accès.
   Cette étape appelle les modèles choisis ; elle peut utiliser le réseau et entraîner des frais.
   Résultat attendu : une ligne `main` et une ligne `fast`, chacune avec taux de réussite,
   total de jetons, nombre d'appels estimés, durée et chemin du résultat enregistré.
   La commande active les experts et alterne les niveaux à chaque incident et répétition.
   Elle demande une température de 0 et une graine fixe lorsque le fournisseur les accepte.
   Certains fournisseurs ignorent la graine : la variance d’échantillonnage demeure.
   Le mode MCP est refusé avant l’évaluation ; utilisez `OPS_ASSIST_TOOLS=inprocess`.
   Les clés des fournisseurs connus du niveau rapide sont vérifiées avant les appels.
   Le coordinateur conserve toujours la chaîne principale et chaque enquête repart à neuf.

4. Comparez les rapports avec `--show-reports` et examinez les échecs par incident.
   Résultat attendu : vous pouvez identifier les critères qui expliquent l'écart de score.
   Le score utilise des règles littérales ; il ne remplace pas une revue humaine des réponses.
   Le total utilise les métadonnées disponibles et estime les autres appels à partir du texte.
   Les appels impossibles à mesurer sont comptés séparément comme inconnus.
   Les appels échoués avant retour ne sont pas comptabilisés ; le total peut donc être incomplet.

## Exercices

1. Sans réseau, modifiez une chaîne rapide dans un profil temporaire et vérifiez `profile`.
2. Expliquez pourquoi les deux passages identiques par défaut ne prouvent pas une distillation.
3. Repérez un cas où un score moyen masque une erreur sur un incident particulier.
4. Proposez un jeu de test indépendant avant d'entraîner un élève sur des sorties autorisées.

## Pour aller plus loin

Comparez plusieurs répétitions et les résultats par catégorie avant toute décision de déploiement.
Étudiez les distributions de sortie, la qualité des exemples et les limites de la licence choisie.
Hors ligne, relisez l'atelier 24 et ses exemples de données fictives, sans lancer d'entraînement.
