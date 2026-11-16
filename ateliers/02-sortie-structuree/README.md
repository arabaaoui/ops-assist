# Atelier 02 — Du prompt au rapport validé

Durée : 30 à 45 minutes. Prérequis : environnement installé avec `uv sync`. Toutes les commandes de cet atelier fonctionnent sans modèle ni réseau.

Un message **system** fixe le rôle et les règles de l'assistant ; le message **user** exprime la question ; les résultats d'outils sont des **données non fiables**. Un journal peut contenir du texte demandant à l'agent d'ignorer ses règles : ce texte reste une observation, pas une instruction. Lisez `src/ops_assist/prompts/investigator.md` et repérez le rôle, la méthode, cette séparation et les règles de sortie.

Une réponse libre est facile à lire mais fragile à analyser : un titre ou une formulation peut changer. Un schéma décrit au contraire les champs et leurs types. Ici, Pydantic valide `IncidentReport` et ses règles de cohérence : les hypothèses citent des indices de faits à partir de zéro, une cause identifiée demande au moins un fait, et aucune action n'est proposée si les données sont insuffisantes. La validation vérifie la structure et la cohérence déclarée, pas la vérité des observations.

Le piège « JSON avant raisonnement » consiste à remplir trop vite les conclusions pour satisfaire le format. Le rapport place les faits avant les hypothèses pour encourager une progression fondée sur les observations ; cet ordre seul ne garantit pas un raisonnement correct.

```bash
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist validate examples/reports/missing-fact.json
uv run ops-assist validate examples/reports/action-insufficient.json
uv run ops-assist validate examples/reports/root-without-facts.json
```

La première commande affiche `OK`. Les trois autres affichent une erreur précise et renvoient le code 1.

## Exercices

1. Ouvrez les fichiers : associez chaque erreur à la règle qu'elle enfreint. Dans le premier exemple invalide, l'indice 9 ne désigne aucun fait.
2. Copiez un exemple invalide dans un fichier temporaire, corrigez-le et relancez `validate` : l'erreur doit disparaître.
3. Ajoutez une donnée fausse mais bien formée : le schéma peut l'accepter. Quelle vérification humaine ou source faudrait-il pour la confirmer ?
