# Atelier 10 — MCP ou skills

## Objectif

Vous allez distinguer un protocole d’accès aux outils d’une méthode d’enquête en instructions.
Vous découvrirez les skills fournis et leur chargement par ADK, sans modèle ni réseau.

## Notions

MCP est un protocole : un client découvre des outils proposés par un serveur, puis les appelle.
Un outil peut par exemple lire des alertes et renvoyer des données avec leur provenance.
Un skill est un ensemble d’instructions destinées à guider l’agent dans une tâche.
Il ne fournit pas à lui seul les données ni l’exécution d’un outil d’observation.
Les deux approches se complètent : MCP fournit l’accès et le skill propose une méthode.

Un skill Agent Skills possède un dossier contenant `SKILL.md`.
Son en-tête YAML entre deux lignes `---` contient `name` et `description`.
Le nom correspond au nom du dossier ; le corps Markdown contient les instructions.
ADK valide les métadonnées et charge les fichiers lors de la création de l’agent.
Son `SkillToolset` propose ensuite `list_skills` et `load_skill` au modèle.
La liste contient les noms et descriptions ; le chargement renvoie les instructions du skill choisi.
Ces instructions guident le modèle : leur sélection et leur suivi ne sont pas garantis.

## Étapes hors ligne

### 1. Lire les méthodes

Depuis la racine du projet, affichez les fichiers distribués :

```bash
cat src/ops_assist/skills/latency/SKILL.md
cat src/ops_assist/skills/errors-5xx/SKILL.md
```

Résultat attendu : deux en-têtes YAML, puis des méthodes distinctes pour la latence et les erreurs 5xx.
Dans les deux cas, l’agent doit distinguer les faits sourcés des hypothèses et des inconnues.

### 2. Charger et valider

```bash
uv run python - <<'PY'
from ops_assist.agent import load_skills

for skill in load_skills():
    print(skill.name, ':', skill.description)
PY
```

Résultat attendu : `latency` et `errors-5xx`, chacun suivi de sa description.
Un fichier mal formé ou des instructions vides empêchent le démarrage et son chemin est indiqué.
Les skills sont inclus dans le paquet ; aucun fournisseur de modèle n’est nécessaire pour les lire.

### 3. Observer la découverte dans la boucle ADK

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_skills.py
```

Résultat attendu : les tests passent ; un modèle scripté découvre les deux skills et charge la méthode de latence.
Pour une enquête interactive, `ops-assist investigate "Pourquoi le paiement est-il lent ?"` utilise le fournisseur configuré.
Avec `OPS_ASSIST_TOOLS=mcp`, les outils d’observation passent par MCP ; les skills restent disponibles.
Le parcours scripté ci-dessus ne nécessite ni fournisseur, ni clé, ni serveur distant.

## Exercices

1. Repérez les étapes communes et les éléments propres à chaque méthode dans les deux fichiers.
2. Dans une copie temporaire d’un skill, retirez `description` et essayez `load_skill_from_dir` : quelle erreur ADK produit-il ?
3. Pour lire une métrique, choisiriez-vous un outil MCP ou un skill ? Justifiez avec le rôle de chacun.
4. Ajoutez sur papier une vérification de dépendance au skill 5xx et indiquez quelle preuve serait nécessaire.

## Pour aller plus loin

Comparez l’instruction générale de l’agent aux deux méthodes : quelles consignes doivent rester communes ?
Un skill est une instruction, pas une preuve : vérifiez toujours les observations et leurs sources.
Avant d’utiliser un skill tiers, examinez aussi ses instructions et ses éventuelles ressources ou scripts.
