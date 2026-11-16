# Atelier 03 — Premier agent

Durée : 30 à 45 minutes. Prérequis : environnement installé et, pour l'exécution interactive, un modèle configuré comme dans l'atelier 01, capable d'appeler des outils. Les données de rejeu sont fictives.

Un agent réunit quatre ingrédients : un **modèle** qui choisit les prochaines étapes, une **instruction** qui définit son rôle, des **outils** qui accèdent aux observations, et une **boucle** qui transmet les résultats au modèle jusqu'à sa réponse. L'agent dispose de cinq outils : alertes, métriques, journaux, changements et rappel de résumés. Dans cet atelier, concentrez-vous sur `get_alerts` et observez les outils choisis.

Dans une boucle souvent appelée **ReAct**, le modèle choisit un outil, reçoit son résultat et décide de la suite. La trace ci-dessous montre les appels et leurs arguments, puis le rapport JSON validé ; elle ne montre pas le raisonnement interne du modèle.

```bash
uv run ops-assist investigate "Pourquoi le paiement est-il lent ?"
uv run ops-assist investigate "Quelle ligne de journal prouve la cause ?" --incident payment-latency
```

Vous pouvez voir `Tool: get_alerts {}` et d'autres appels, puis un rapport. Si l'agent ne consulte que les alertes, elles ne permettent pas de connaître une ligne de journal ni de prouver la cause. Sinon, examinez les preuves citées et toute affirmation non étayée. La sortie dépend du modèle ; le schéma vérifie sa cohérence, pas sa véracité.

## Exercices

1. Associez chaque appel affiché à une étape de la boucle. Quelle information revient au modèle après `get_alerts` ? Consultez `alerts.json` pour comparer.
2. Posez une question à laquelle les alertes ne répondent pas. Vérifiez que le rapport exprime l'incertitude ; si ce n'est pas le cas, repérez ce que les preuves ne permettent pas de conclure.
3. Pour explorer visuellement, lancez `uv run adk web apps` et ouvrez l'adresse locale affichée ; sélectionnez l'agent et posez la même question. L'interface nécessite elle aussi un modèle configuré.

**Sans modèle** : lisez `tests/test_agent_loop.py` et `tests/test_workshops.py`, puis exécutez `uv run pytest -q`. Le modèle scripté appelle réellement l'outil de rejeu et produit un rapport sans réseau ni clé.
