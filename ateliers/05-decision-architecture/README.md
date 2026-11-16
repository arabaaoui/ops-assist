# Atelier 05 — Workflow ou agent

Durée : 40 à 50 minutes. Préparez les dépendances avec `uv sync` si nécessaire.
Les données et services de cet atelier sont fictifs. Les étapes ci-dessous sont hors ligne.

## Objectif

Comparer un pré-triage déterministe et une investigation autonome.

## Notions à rappeler

Un workflow applique des règles définies à l’avance.
Un agent peut choisir ses prochains outils selon les résultats.
L’autonomie coûte des appels, ajoute de la variabilité et nécessite des garde-fous.
Une coïncidence temporelle indique un candidat, pas une cause démontrée.

## Étapes

Depuis la racine du dépôt, exécutez :

```bash
uv run ops-assist triage --incident payment-latency
cat src/ops_assist/data/incidents/payment-latency/changes.json
cat docs/decisions/0001-pretriage-workflow-then-agent.md
```

Résultats attendus :

- Le tri cite `DEP-2140` et les deux alertes de `payment-api`.
- Le changement a lieu à 08:55 et la première alerte à 09:02.
- `DEP-0870` concerne `orders-db` et date du 10 mars : il est exclu.

Poursuivez la lecture :

- Repérez la première alerte et les services affectés dans la sortie.
- Comptez les minutes entre le changement retenu et cette alerte.
- Comparez le service et la date du changement exclu.
- Lisez les quatre options et la décision dans l’ADR.
- Le bloc de pré-triage sert de point de départ à l’agent.
- L’agent doit encore consulter les preuves avant de conclure.

## Exercices

1. Imaginez une règle déterministe suffisante pour une notification. Observez ses entrées et sa sortie.

2. Imaginez un incident où un service dépend d’un autre. Observez ce que la règle locale pourrait manquer.

3. Comparez un prompt unique et le workflow suivi d’un agent. Observez coût, répétabilité et flexibilité.

4. Déplacez mentalement un changement à 61 minutes avant l’alerte. Observez son exclusion malgré sa pertinence possible.

## Pour aller plus loin

Proposez une mesure de qualité avant de modifier la fenêtre de 60 minutes.

Vous pouvez effectuer cet atelier sans appel de modèle ni accès réseau.
Les exemples sont pédagogiques : une validation de format ne prouve pas une cause.
Comparez vos réponses avec les observations et explicitez les incertitudes.


Prenez quelques minutes pour noter une limite et une question à explorer.
