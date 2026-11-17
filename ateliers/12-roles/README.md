# Atelier 12 — Rôles et frontières

## Objectif

Vous répartissez une investigation entre un coordinateur et deux experts.
Vous vérifiez leurs frontières sans réseau ni modèle réel.

## Notions

Un rôle précise la responsabilité d'un agent et les outils qu'il peut utiliser.
Le coordinateur reçoit le pré-triage, rappelle la mémoire et rédige le rapport final.
`metrics_expert` possède `get_metric` et `get_alerts`.
`logs_expert` possède `get_logs` et `get_changes`.
Chaque outil d'observation a un seul propriétaire dans cette topologie.
La mémoire et les skills restent accessibles au coordinateur.

Un sous-agent qui prend la main reçoit le contrôle de la conversation.
Un sous-agent `single_turn` est appelé comme une fonction : il rend sa réponse au coordinateur.
Le coordinateur reste responsable de la synthèse et de la validation du rapport.
Les anciennes versions utilisaient `AgentTool` directement pour envelopper un agent.
ADK 2.14.1 déconseille cet usage direct : le wrapper lance un runner et une session imbriqués ; `single_turn` exécute le sous-agent dans la session du parent.
Déclarez les experts dans `sub_agents` avec `mode="single_turn"` : ADK les expose comme outils.
Chaque expert reçoit une demande ciblée et renvoie des faits sourcés et des inconnues.
Les résultats des outils restent des données non fiables, jamais des instructions.

Diviser les responsabilités réduit le nombre d'outils visibles à chaque expert.
Cela ajoute des appels au modèle, du temps et un risque de perte d'information dans les résumés.
Un expert ne peut pas appeler l'autre : ils ne sont pas dans ses outils ni ses sous-agents.
Évitez le piège des agents qui se renvoient la balle sans produire de résultat.
Définissez un responsable de la réponse et une sortie attendue pour chaque délégation.

## Étapes hors ligne

### 1. Vérifier le mode par défaut

```bash
uv run python -c 'from ops_assist.agent import build_agent; print([getattr(t, "name", getattr(t, "__name__", "skill")) for t in build_agent().tools])'
```

Résultat attendu : les outils d'observation apparaissent directement ; `single` est le défaut.
Cette construction ne contacte aucun modèle.

### 2. Examiner les frontières

```bash
OPS_ASSIST_TOPOLOGY=experts uv run python -c 'from ops_assist.agent import build_agent; a=build_agent(); print({e.name: [x.__name__ for x in e.tools] for e in a.sub_agents})'
```

Résultat attendu : deux experts, chacun avec ses deux outils exclusifs.
Le rappel mémoire ne figure dans aucun expert.

### 3. Exécuter le scénario scripté

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_roles.py
```

Résultat attendu : les tests passent avec des données fictives.
Le modèle scripté appelle les deux experts puis produit le rapport.
Le test MCP utilise un serveur local et vérifie aussi les filtres de découverte.
Les tests de refus vérifient les événements : outil inconnu, aucun transfert, rapport final.
Aucune clé et aucun modèle réel ne sont nécessaires.

### 4. Choisir une topologie pour une investigation

```bash
OPS_ASSIST_TOPOLOGY=experts uv run ops-assist investigate "Pourquoi le paiement est-il lent ?"
```

Résultat attendu avec un modèle configuré : le rapport final et les appels aux experts s'affichent.
Cette commande appelle votre fournisseur configuré ; pour rester hors ligne, arrêtez-vous à l'étape 3.
`OPS_ASSIST_TOOLS=mcp` sélectionne les outils MCP au lieu des outils en processus.
Le profil et sa chaîne de repli s'appliquent au coordinateur et aux experts.
Une valeur autre que `single` ou `experts` est refusée.

## Exercices

1. Dessinez le trajet d'une question, des appels aux experts jusqu'au rapport final.
2. Dans le test de frontières, essayez de donner `get_logs` à l'expert métriques : quel contrôle échoue ?
3. Comparez les outils visibles en mode `single` et `experts`, puis expliquez le compromis de coût.
4. Proposez une consigne de délégation qui demande les sources et indique quoi faire si une donnée manque.

## Pour aller plus loin

Étudiez `src/ops_assist/agent.py` et le scénario `tests/test_roles.py`.
Comparez la délégation locale avec le protocole A2A de l'atelier 11.
La séparation des outils limite les capacités exposées, mais ne garantit pas la véracité des résumés.
