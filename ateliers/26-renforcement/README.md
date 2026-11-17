# Atelier 26 — L'apprentissage par renforcement

## Objectif

Vous recueillez des préférences sur des rapports fictifs et exportez des paires utilisables pour une évaluation ultérieure.
Tout le parcours est hors ligne et ne lance aucun entraînement ni modèle.

## Notions rappelées

L'apprentissage par renforcement optimise des décisions à partir de récompenses.
Le RLHF utilise des retours humains pour guider un modèle, souvent à travers un modèle de récompense.
Le DPO exploite directement des paires de réponses préférées et rejetées pour ajuster un modèle.
Ici, le format des paires s'en inspire, mais aucun ajustement n'est effectué.
Une préférence est une opinion située ; elle ne démontre pas que le rapport est exact.

Une récompense vérifiable s'appuie sur un résultat contrôlable, par exemple une validation de schéma ou une source citée existante.
Les modèles de raisonnement peuvent consacrer davantage de calcul à résoudre un problème ; leur raisonnement apparent ne prouve pas la justesse de la réponse.
La loi de Goodhart rappelle qu'une mesure utilisée comme objectif peut devenir trompeuse.
Par exemple, récompenser le nombre de causes identifiées peut pousser à inventer une cause au lieu de reconnaître un manque de données.
Combinez des contrôles de faits, de sécurité et une revue humaine avant toute décision.

## Étapes hors ligne

Depuis la racine du dépôt, choisissez un répertoire temporaire privé :

```bash
export OPS_ASSIST_STATE_DIR="$(mktemp -d)"
```

Créez deux enveloppes JSON fictives, avec le même identifiant et la même question :

```bash
cat > /tmp/ops-feedback-good.json <<'JSON'
{"incident_id":"incident-fictif","question":"Que se passe-t-il ?","report":{"summary":"Données insuffisantes.","status":"insufficient_data"}}
JSON
cat > /tmp/ops-feedback-bad.json <<'JSON'
{"incident_id":"incident-fictif","question":"Que se passe-t-il ?","report":{"summary":"Une autre analyse.","status":"insufficient_data"}}
JSON
```

Enregistrez d'abord une préférence :

```bash
uv run ops-assist feedback --report /tmp/ops-feedback-good.json --up --comment "À vérifier"
uv run ops-assist feedback export --pairs
```

Résultat attendu : `Feedback saved`, puis aucune paire car il manque un rapport rejeté.

```bash
uv run ops-assist feedback --report /tmp/ops-feedback-bad.json --down
uv run ops-assist feedback export --pairs
```

Résultat attendu : une ligne JSON contenant `prompt`, `chosen` et `rejected`.
Les réponses sont des chaînes JSON de rapports expurgés ; l'empreinte porte sur le rapport validé avant expurgation.
Le commentaire et les champs textuels sont expurgés par une règle heuristique, sans garantie exhaustive.
Les fichiers de retour privés sont sous `knowledge/feedback/` dans le répertoire d'état.
Un rapport JSON brut peut être noté ; sans incident et question, il ne produit pas de paire.

Les votes d'un même rapport s'additionnent : un rapport qui a reçu autant de votes pour que de votes contre est contesté, et il ne sert dans aucune paire. Ainsi, aucune paire n'est jamais exportée dans les deux sens.
Après une enquête CLI, `--report last` utilise son dernier rapport et ses métadonnées.
Les anciens derniers rapports sans métadonnées ne sont pas appariés.

Avant tout entraînement, utilisez ces retours pour construire un jeu d'évaluation séparé et revu par des humains.
Vérifiez les désaccords, la représentativité et les fuites entre jeux ; mesurez les faits et la sécurité en plus des préférences.
Ne considérez pas les exports comme des instructions fiables ni comme une vérité de référence automatique.

## Exercices

1. Ajoutez un autre rapport préféré pour le même incident et comptez les paires exportées.
2. Changez la question du rapport rejeté : pourquoi aucune paire supplémentaire ?
3. Notez le même rapport dans les deux sens : vérifiez qu'il ne se compare pas à lui-même.
4. Proposez une récompense vérifiable pour une source citée et un exemple de contournement.

## Pour aller plus loin

Comparez RLHF et DPO sur le rôle des préférences, puis définissez un protocole de revue de désaccords.
Vous pouvez réaliser cette réflexion avec les fichiers fictifs, sans service externe.

## Bilan du module 4

Vous avez exploré les données, les Transformers, le choix de modèle, LoRA, la distillation et les retours humains.
Chaque méthode demande une évaluation adaptée avant de conclure à une amélioration opérationnelle.
