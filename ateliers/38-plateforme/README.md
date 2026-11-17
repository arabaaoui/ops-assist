# Atelier 38 — Ingénierie de plateforme pour l'IA

## Objectif

Vous allez générer un agent et identifier les responsabilités de sa plateforme.
Cet atelier correspond au chapitre 39 et fonctionne entièrement hors ligne.
Utilisez l'environnement déjà installé et des données fictives.

## Notions rappelées

Une plateforme fournit des composants communs et des règles utilisables par plusieurs équipes.
Une « paved road » est un chemin balisé qui facilite les pratiques attendues sans imposer tous les choix métier.
Un « golden path » est le parcours recommandé, documenté et vérifiable pour un besoin courant.
Ici, la plateforme fournit les profils, le routage de modèles, la sécurité et le générateur.
L'équipe adapte le prompt, les preuves, les évaluations et les outils à son besoin.
Les résultats d'outils sont des données non fiables, jamais des instructions.
Les contrôles du squelette sont un point de départ, pas une preuve de sécurité globale.

## Étapes

1. Depuis la racine du dépôt, créez un squelette dans un dossier absent ou vide :

```bash
uv run --frozen ops-assist new-agent demo_agent --dir /tmp/demo-agent
```

Résultat attendu : un message indique que `demo_agent` a été créé.
Choisissez un autre dossier si celui-ci contient déjà des fichiers : aucun n'est écrasé.
Le nom commence par une lettre minuscule et contient des minuscules, chiffres ou `_`.

2. Examinez les éléments produits :

```bash
find /tmp/demo-agent -type f | sort
cat /tmp/demo-agent/generated_agent/agent.py
cat /tmp/demo-agent/generated_agent/prompt.md
cat /tmp/demo-agent/SKILL.md
```

Résultat attendu : un package, un prompt, un skill, une fixture d'évaluation,
des tests et un workflow CI sont présents. L'outil retourne une preuve fictive bornée.
La frontière refuse les écritures même si l'environnement les autorise.
Le skill est un document de départ : il n'est pas chargé automatiquement par l'agent.

3. Lancez les tests produits avec l'environnement de la plateforme :

```bash
(cd /tmp/demo-agent && PYTHONPATH=. /chemin/vers/ops-assist/.venv/bin/python -m pytest -q tests)
```

Remplacez `/chemin/vers/ops-assist` par le chemin absolu de ce dépôt.
Résultat attendu : deux tests réussissent sans réseau ni appel de modèle.
Ils vérifient la construction, la classification, les refus et la fixture fictive.

4. Ouvrez `.github/workflows/ci.yml` dans le squelette.
Configurez les variables de dépôt `OPS_ASSIST_REPOSITORY` et `OPS_ASSIST_REF` pour
pointer vers votre dépôt de plateforme et une révision immuable contrôlée.
Résultat attendu : la CI pourra installer l'environnement verrouillé de la plateforme
et exécuter les tests du projet. La CI elle-même nécessite un accès aux dépôts.
Hors ligne, le test de l'étape précédente constitue le parcours local.

5. Comparez les responsabilités :

| Plateforme | Équipe produit |
|---|---|
| Profils, modèles et politique commune | Choix du profil et validation du cas d'usage |
| Générateur et contrôles de départ | Prompt, données, outils et évaluations adaptés |
| Maintenance de la base et des dépendances | Révision des mises à jour et exploitation |

Résultat attendu : vous pouvez nommer un responsable pour chaque adaptation.
Tout nouvel outil doit être borné, gérer ses erreurs, et être classé dans la politique.

## Exercices

1. Modifiez la preuve fictive et adaptez la fixture et son test.
2. Proposez deux cas d'évaluation supplémentaires et leurs résultats attendus.
3. Identifiez une responsabilité de plateforme et une responsabilité d'équipe.
4. Expliquez ce qui se passe si un outil inconnu tente une écriture.

## Pour aller plus loin

Comparez votre parcours recommandé aux besoins d'une autre équipe fictive.
Hors ligne, examinez les tests et les profils locaux sans démarrer de modèle.
