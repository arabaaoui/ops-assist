# Atelier 33 — Les évaluations

## Objectif

Mesurer la réussite de rapports d'incident, puis appliquer un seuil de publication explicite.
Cet atelier correspond au chapitre 34 du cours.
Vous pouvez réaliser toutes les étapes hors ligne avec les fichiers fictifs fournis.

## Notions rappelées

Une évaluation hors ligne note des rapports déjà enregistrés, sans appeler de modèle.
Une évaluation en ligne relance les investigations sur les incidents enregistrés.
Elle utilise le fournisseur configuré et peut donc nécessiter un service de modèle.
Les mêmes contrôles déterministes vérifient validité, statut, cause, sources et conclusions interdites.
Ces contrôles lexicaux ne comprennent pas réellement le sens : inspectez les erreurs et les faux positifs.
Un LLM utilisé comme juge ajouterait coût, variance et biais, et ne garantirait pas une vérité de référence.
Il n'est pas utilisé ici ; les réponses attendues et les règles rendent la notation reproductible.

Un taux de réussite est le nombre de rapports réussis divisé par le nombre total de rapports.
Les erreurs d'investigation comptent comme des échecs, elles restent dans le dénominateur.
Le taux par incident révèle les cas fragiles que la moyenne globale peut masquer.
`--repeat N` répète chaque incident : les sorties d'un modèle peuvent varier entre essais.
Même une graine fixe ne garantit pas la reproductibilité chez tous les fournisseurs.
Plusieurs essais exposent cette variance, sans constituer une garantie statistique sur six cas.

Un seuil est une règle de décision, pas une mesure universelle de qualité.
Le fichier `src/ops_assist/evals/threshold.yaml` associe la valeur 0,8 au jeu 1.1.0 et explique son choix.
Avec six essais, 5 réussites sur 6 franchissent ce seuil ; 4 sur 6 ne le franchissent pas.
Ce choix pédagogique tolère un échec et ne démontre pas qu'une version est prête pour la production.
La porte refuse un jeu d'une autre version : une nouvelle version exige de revoir le seuil.

## Étapes hors ligne

1. Affichez les cas et leur version :

   ```sh
   uv run ops-assist eval list
   ```

   Résultat attendu : six incidents fictifs et la version `1.1.0`.

2. Notez le rapport de référence déjà enregistré :

   ```sh
   uv run ops-assist eval check-reports tests/fixtures/evaluation/passing
   ```

   Résultat attendu : `PASS`, puis un taux de `100.0%` ; le code de sortie vaut zéro.
   Chaque fichier JSON brut porte l'identifiant de l'incident comme nom, par exemple `payment-latency.json`.
   Une enveloppe sauvegardée peut aussi porter `incident_id` et `report`.

3. Essayez la donnée volontairement erronée, réservée aux tests :

   ```sh
   uv run ops-assist eval check-reports tests/fixtures/evaluation/failing
   ```

   Résultat attendu : `FAIL`, taux de `0.0%` et code de sortie non nul.
   Un fichier JSON invalide ou un incident inconnu échoue aussi ; un dossier vide est refusé.
   Cette commande évalue les fichiers présents, sans exiger la couverture de tous les incidents.

4. Facultatif, si votre fournisseur de modèle est disponible et configuré :

   ```sh
   uv run ops-assist eval run --profile local --repeat 3 --gate
   ```

   Résultat attendu : résultats par essai et taux par incident et global ; la porte renvoie un code non nul sous le seuil ou en cas de version différente.
   Sans fournisseur, restez sur les étapes précédentes : aucun appel de modèle n'est nécessaire.

## Exercices

1. Calculez les taux par incident et global pour trois incidents avec respectivement 3/3, 2/3 et 0/3 réussites.
2. Copiez un rapport dans un dossier temporaire, modifiez son statut et observez le changement du score hors ligne.
3. Expliquez pourquoi un seuil de 80 % sur six cas ne suffit pas à caractériser un risque rare.
4. Proposez un autre seuil et justifiez-le selon le coût des échecs et la variance observée ; ne modifiez la politique qu'après revue.

## Pour aller plus loin

Comparez deux séries de répétitions avec la même configuration et examinez chaque incident instable.
Ajoutez des cas fictifs représentatifs en versionnant le jeu et en réévaluant le seuil.
Gardez un jeu indépendant pour mesurer la généralisation : le jeu public présent peut être appris indirectement.
