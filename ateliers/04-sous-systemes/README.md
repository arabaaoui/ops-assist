# Atelier 04 — Les cinq sous-systèmes

Durée : 40 à 50 minutes. Préparez les dépendances avec `uv sync` si nécessaire.
Les données et services de cet atelier sont fictifs. Les étapes ci-dessous sont hors ligne.

## Objectif

Identifier le rôle de chaque événement d’une enquête.

## Notions à rappeler

La perception reçoit les observations ; le raisonnement choisit quoi examiner.
L’action appelle un outil, la communication produit le rapport.
La mémoire conserve des résumés : elle permet de retrouver des expériences, sans entraîner le modèle.
Un même événement peut traverser plusieurs sous-systèmes ; distinguez émission et réception.

## Étapes

Depuis la racine du dépôt, exécutez :

```bash
uv run ops-assist triage
uv run pytest -q tests/test_agent_loop.py
cat docs/architecture.md
```

Résultats attendus :

- Le tri affiche `payment-api`, les alertes et `DEP-2140`.
- Le test doit réussir ; son modèle scripté appelle `get_alerts` sans réseau.
- Le document décrit les cinq sous-systèmes et leurs limites.

Poursuivez la lecture :

- Ouvrez `tests/test_agent_loop.py` et repérez l’appel `get_alerts`.
- Classez son émission comme action, puis sa réponse comme perception.
- Repérez la construction du rapport et classez-la comme communication.
- Identifiez le moment où le modèle décide d’appeler l’outil : raisonnement.
- Examinez ensuite `src/ops_assist/memory.py` : la mémoire conserve un résumé.
- Notez que cette conservation n’est pas un apprentissage des poids.

## Exercices

1. Dans le test scripté, associez chaque événement au sous-système correspondant. Observez les frontières entre appel et résultat.

2. Dans le diagramme, suivez le trajet d’une alerte jusqu’au rapport. Observez les retours possibles.

3. Retrouvez l’instruction qui distingue faits et hypothèses. Observez son rôle dans le raisonnement.

4. Cherchez une fonction absente : pourquoi la communication entre agents est-elle encore future ? Observez les interfaces disponibles.

## Pour aller plus loin

Dessinez une source réelle fictive et indiquez où elle remplacerait le rejeu.

Vous pouvez effectuer cet atelier sans appel de modèle ni accès réseau.
Les exemples sont pédagogiques : une validation de format ne prouve pas une cause.
Comparez vos réponses avec les observations et explicitez les incertitudes.


Prenez quelques minutes pour noter une limite et une question à explorer.
