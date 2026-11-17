# Atelier 37 — Pourquoi les projets échouent

## Objectif

Vous allez appliquer cinq causes d'échec à votre projet et décider des actions prioritaires.
Cet atelier correspond au chapitre 38 et peut être réalisé entièrement hors ligne.
Utilisez uniquement des données fictives dans vos exemples.

## Notions rappelées

Un besoin décrit un résultat observable pour ses utilisateurs.
Les données doivent être accessibles, adaptées et suffisamment fraîches.
La validation compare le résultat attendu aux résultats observés et cherche les limites.
Un budget associe les ressources consommées à une unité utile, ici une investigation.
Un responsable nommé peut décider, suivre les écarts et organiser les corrections.
Une preuve est un élément vérifiable ; une intention seule ne démontre pas un résultat.
Une mesure de jetons ne suffit pas toujours à calculer une facture complète.

## Étapes

1. Lisez la revue fournie depuis la racine du dépôt :

```bash
cat docs/failure-review.md
```

Résultat attendu : cinq causes, leurs preuves, leurs limites et un responsable à désigner.
Suivez les liens vers le code et les tests pour vérifier les affirmations.

2. Vérifiez deux contrôles reproductibles sans modèle ni réseau :

```bash
uv run --frozen ops-assist eval check-reports tests/fixtures/evaluation/passing
uv run --frozen ops-assist redteam --fast
```

Résultat attendu : les rapports fictifs passent et les sondes rapides réussissent.
Utilisez un environnement déjà installé et un cache rempli si vous êtes hors ligne.
Ces contrôles ne prouvent pas la qualité de toutes les réponses d'un modèle réel.

3. Examinez le coût simulé :

```bash
uv run --frozen ops-assist eval cost --json
```

Résultat attendu : des scénarios de coût par incident fictif, avec `null` si un prix manque.
Ce sont des estimations scénarisées, pas les coûts mesurés d'une investigation réelle.
Pour un cas réel, rapprochez les jetons disponibles des prix et de la facture du fournisseur.
Hors ligne, conservez le scénario fictif et notez les informations manquantes.

4. Préparez votre propre grille, sur papier ou dans un fichier local :

| Cause | Constat et preuve | Limite | Action et délai | Responsable |
|---|---|---|---|---|
| Besoin flou | | | | |
| Données manquantes | | | | |
| Validation absente | | | | |
| Coût non maîtrisé | | | | |
| Responsable absent | | | | |

Résultat attendu : chaque ligne contient un constat vérifiable ou une lacune explicite.
Pour le besoin, choisissez une mesure initiale et une cible de délai de diagnostic.
Pour les coûts, choisissez une unité, un budget et une méthode de rapprochement.
Attribuez chaque action à une personne et classez-la selon sa criticité et son délai.

## Exercices

1. Formulez un besoin mesurable et décrivez comment établir sa valeur initiale.
2. Choisissez une donnée manquante et décrivez comment vérifier sa fraîcheur.
3. Proposez un test de validation et une attaque que ce test ne couvre pas.
4. Calculez un coût fictif par investigation et indiquez les frais exclus.

## Pour aller plus loin

Comparez votre grille avant et après une prochaine modification du projet.
Hors ligne, relisez les preuves locales et notez les décisions qui restent à prendre.
