# Atelier 39 — Passer à l'échelle de l'entreprise

## Objectif

Vous allez examiner le registre d'un agent fictif et préparer sa gouvernance.
Cet atelier correspond au chapitre 40 et fonctionne entièrement hors ligne.

## Notions rappelées

Un registre recense les agents, leur finalité, leurs outils et leurs responsables.
Un propriétaire identifiable prend en charge les décisions, les incidents et les revues.
Le format Component de Backstage fournit une identité et un cycle de vie communs.
La section `spec.agent` ajoute les informations propres à cet agent.
Les droits déclarés décrivent le périmètre prévu ; la politique de sécurité décide à l'exécution.
Les outils inconnus sont classés en écriture par défaut et exigent les contrôles associés.
Un budget mensuel facilite le suivi des dépenses, mais une valeur déclarée ne bloque rien.
Les évaluations mesurent des cas définis ; elles ne prouvent pas la sûreté générale.
Un identifiant de modèle enregistré peut être un alias modifiable chez son fournisseur.
Le registre documente les identifiants des profils fournis, sans figer les surcharges locales.

## Étapes

1. Depuis la racine du dépôt, inspectez le catalogue :

```bash
cat catalog-info.yaml
```

Résultat attendu : un Component expérimental avec un propriétaire à désigner,
une finalité, des outils classés, des droits, des profils et un budget fictif en USD.
Le budget est indicatif : aucun suivi ni plafond automatique n'est installé.

2. Comparez la déclaration à la politique et à la construction de l'agent :

```bash
rg -n 'TOOL_ACCESS|rollback_deployment' src/ops_assist/security.py
rg -n 'tools=|SkillToolset' src/ops_assist/agent.py
```

Résultat attendu : les observations sont en lecture et le retour arrière en écriture.
Celui-ci exige une activation explicite et une confirmation humaine ; le réel le refuse.
L'outil de script ADK est classé en écriture par défaut car il est inconnu de la table.
Les outils de skills, experts et topologies sont inclus dans l'inventaire.
Leurs résultats restent des données non fiables, jamais des instructions.

3. Vérifiez automatiquement la cohérence, sans modèle ni réseau :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/pytest -q tests/test_catalog.py
```

Résultat attendu : le test réussit ; il compare les outils construits et leur classification.
Il contrôle aussi les profils fournis, les liens et les champs de gouvernance.
Il ne vérifie pas les extensions dynamiques ou profils externes propres à un déploiement.

4. Examinez les preuves de validation et le suivi des changements :

```bash
cat src/ops_assist/evals/threshold.yaml
cat BEHAVIOR_CHANGELOG.md
```

Résultat attendu : une politique de seuil et un historique de comportement sont présents.
Les résultats d'évaluation propres à un déploiement restent à enregistrer séparément.

5. Préparez une revue pour deux équipes fictives.
Désignez un propriétaire, une personne de relais et un rythme de revue du catalogue.
Comparez les dépenses observées au budget et attribuez le traitement des dépassements.
Résultat attendu : chaque responsabilité a un titulaire et une action de suivi.

## Exercices

1. Proposez un propriétaire et un relais fictifs, puis expliquez leurs responsabilités.
2. Ajoutez sur une copie du catalogue un outil fictif et prévoyez le résultat du test.
3. Définissez une alerte et une action humaine pour un dépassement de budget.
4. Expliquez pourquoi un alias de modèle et une évaluation passée ne suffisent pas à figer le comportement.

## Pour aller plus loin

Comparez les catalogues de plusieurs agents fictifs et repérez les droits communs.
Hors ligne, examinez les profils et les évaluations fournis sans lancer de modèle.
