# Atelier 06 — La mémoire d’un agent

Durée : 40 à 50 minutes. Préparez les dépendances avec `uv sync` si nécessaire.
Les données et services de cet atelier sont fictifs. Les étapes ci-dessous sont hors ligne.

## Objectif

Distinguer contexte, état de session et mémoire à long terme.

## Notions à rappeler

Le contexte est ce que le modèle reçoit pour un tour.
L’état de session conserve les événements et le rapport pendant une enquête.
La mémoire à long terme stocke des résumés retrouvables par service entre enquêtes.
La persistance des sessions et la mémoire sont deux mécanismes distincts.

## Étapes

Depuis la racine du dépôt, exécutez :

```bash
export OPS_ASSIST_MEMORY_DIR=/tmp/ops-assist-atelier-memory
uv run ops-assist memory list
uv run pytest -q tests/test_module1.py -k memory
uv run pytest -q tests/test_sessions.py
uv run ops-assist memory forget --service payment-api
```

Résultats attendus :

- La liste affiche `[]` si aucun résumé n’a été enregistré dans ce dossier.
- Les tests réussissent ; ils utilisent des données fictives, une base temporaire et un modèle scripté.
- Le test de session vérifie que les événements précédents sont transmis au tour suivant.
- La commande forget ne produit pas de sortie ; elle retire les résumés du service.

Poursuivez la lecture :

- Une enquête validée enregistre son résumé pour chaque service affecté.
- L’outil de rappel renvoie au plus dix résumés récents.
- Par défaut, la session ADK reste en mémoire vive.
- `OPS_ASSIST_SESSION_DB=/tmp/ops-assist-sessions.db` active sa persistance SQLite.
- La CLI affiche l’identifiant de session après une enquête.
- Avec un modèle configuré, passez `--session ID` pour reprendre ou créer cette session.
- Réutilisez le même fichier SQLite : une autre base ne contient pas cet historique.
- Les événements de session et les résumés JSON sont deux stockages distincts.
- SQLite peut contenir messages et résultats d’outils non expurgés : protégez le fichier.
- La mémoire conserve uniquement le résumé du rapport, qui peut recopier une ligne de journal.
- Le filtre de secrets est simple : il ne garantit pas l’absence de données sensibles.

## Exercices

1. Comparez contexte, événements de session SQLite et résumés JSON. Observez leur portée et leur durée de vie.

2. Lisez `src/ops_assist/memory.py` et repérez les champs conservés. Observez que seuls service et résumé sont enregistrés ; le résumé peut reprendre des extraits de journaux.

3. Lisez `tests/test_sessions.py` : suivez les deux enquêtes scriptées. Observez les événements repris et le rapport enregistré.

4. Oubliez ce service puis listez à nouveau. Observez que les autres services restent présents.

## Pour aller plus loin

Imaginez une politique de durée de conservation distincte pour les sessions SQLite et les résumés JSON.

Vous pouvez effectuer cet atelier sans appel de modèle ni accès réseau.
Les exemples sont pédagogiques : une validation de format ne prouve pas une cause.
Comparez vos réponses avec les observations et explicitez les incertitudes.

Prenez quelques minutes pour noter une limite et une question à explorer.
