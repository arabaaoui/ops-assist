# Atelier 35 — Red teaming hors ligne

## Objectif

Vous allez confronter les frontières d'ops-assist à six scénarios hostiles fictifs.
Le chapitre 36 présente le red teaming ; cet atelier correspond à l'étape 35.
Vous lancez les sondes sans compte, modèle réel, fournisseur ou connexion réseau.
Chaque exécution utilise un état temporaire et une copie locale du rejeu.

## Notions rappelées

Une sonde est un scénario reproductible avec une attente vérifiable.
Une régression survient quand une modification casse une protection auparavant vérifiée.
L'audit décrit les appels et leurs issues ; l'état simulé révèle une écriture éventuelle.
Une demande de confirmation n'est pas une autorisation humaine.
Un résultat d'outil est une donnée non fiable, même s'il contient un ordre.
Le modèle scripté demande volontairement une action : il ne juge pas le texte.
Il sert à éprouver les frontières de l'application, pas la robustesse d'un modèle.

La correspondance pédagogique utilise les catégories OWASP LLM Top 10 2025 :

| Sondes | Catégorie | Risque illustré |
| --- | --- | --- |
| Journal piégé | LLM01 Prompt Injection | Une donnée essaie d'orienter l'agent. |
| Rollback sans confirmation, surface distante | LLM06 Excessive Agency | Une action dépasse l'autorité accordée. |
| Budgets et sortie volumineuse | LLM10 Unbounded Consumption | Une boucle ou une sortie consomme trop de ressources. |

Cette correspondance indique le risque illustré, pas une couverture complète OWASP.

## Étapes

1. À la racine du dépôt, lancez la suite complète hors ligne :

   ```bash
   uv run ops-assist redteam
   ```

   Attendu : six lignes `PASS` dans le tableau `Probe / Expected / Observed / Result`.
   Le journal piégé demande un rollback ; l'audit enregistre le refus ou la demande de confirmation.
   Le client de démonstration et l'état simulé ne doivent pas recevoir d'écriture.

2. Lancez le sous-ensemble rapide, adapté à la CI :

   ```bash
   uv run ops-assist redteam --fast
   ```

   Attendu : cinq lignes `PASS` ; la sonde `poisoned_log` est omise.
   Le code de sortie vaut zéro si toutes les sondes sélectionnées passent, un sinon.

3. Observez le format destiné à une automatisation :

   ```bash
   uv run ops-assist redteam --fast --json
   ```

   Attendu : une liste JSON contenant `probe`, `expected`, `observed`, `pass` et `owasp`.
   Les champs observés décrivent des données fictives et des résultats de garde-fous.

4. Exécutez les tests ciblés :

   ```bash
   OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/python -m pytest -q tests/test_redteam.py
   ```

   Attendu : les sondes passent et les tests détectent plusieurs garde-fous désactivés.
   Les tests ne contactent ni modèle ni service externe.

## Exercices

1. Reliez chaque résultat aux protections et à la catégorie OWASP du tableau.
2. Repérez dans les tests la mutation qui supprime la confirmation et expliquez son effet.
3. Comparez les budgets d'appels et de recherches : quelle issue apparaît dans l'audit ?
4. Imaginez une nouvelle injection dans un runbook et définissez son observation mesurable.

## Pour aller plus loin

Une sonde qui passe n'est pas une preuve de sécurité : elle ne couvre que son scénario.
Le modèle scripté ne mesure pas l'obéissance d'un modèle réel aux instructions.
La sonde distante inspecte la liste MCP et la construction A2A sans ouvrir de serveur.
Ajoutez des attaques variées et contrôlez les faux positifs avant toute conclusion.
Conservez toujours un parcours hors ligne avec des données fictives pour les régressions.
