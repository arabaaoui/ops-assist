# Atelier 01 — Premier appel et tokens

Durée : 30 à 45 minutes. Cet atelier accompagne la vidéo « Le LLM de l'intérieur » : revenez à cette vidéo pour les notions de découpage et de fenêtre de contexte. Les données de l'incident sont fictives. Depuis la racine du projet, préparez l'environnement avec `uv sync` si nécessaire, puis lancez les commandes avec `uv run`.

Un **token** est une unité de texte manipulée par un modèle : ce n'est ni toujours un mot ni toujours un caractère. Le découpage dépend du tokenizer et du modèle. La **fenêtre de contexte** limite la quantité de tokens que le modèle peut prendre en compte, instructions et réponse comprises. Compter les seuls fichiers donne donc une estimation partielle du budget.

```bash
uv run ops-assist profile
uv run ops-assist tokens
uv run ops-assist tokens --incident payment-latency --model gemini/gemini-2.5-flash
```

Le tableau compte les caractères et les tokens de chaque fichier enregistré, sauf `expected.json`, réservé à l'évaluation. Le tokenizer Anthropic fourni avec LiteLLM est utilisé localement pour tous les modèles : c'est une approximation, pas le compteur exact du modèle choisi. Le pourcentage est affiché si LiteLLM connaît la taille d'entrée du modèle. Les journaux (`logs.jsonl`) dominent ici en caractères ; les métriques peuvent toutefois dépasser leur nombre de tokens avec ce tokenizer. Comparez aussi les alertes et réfléchissez au coût d'envoyer toutes les lignes à chaque question.

## Premier appel facultatif

`ask` envoie une question simple au premier modèle du profil, sans outil ni agent et sans repli automatique. Choisissez une option :

- **Local** : installez et démarrez Ollama, puis téléchargez le modèle une fois avec `ollama pull qwen3:8b`. La commande `uv run ops-assist ask "Expliquez la latence en une phrase"` utilise le profil local par défaut.
- **Gemini** : définissez `OPS_ASSIST_PROFILE=gemini` et `GEMINI_API_KEY` (`api` reste un alias).
- **OpenAI** : définissez `OPS_ASSIST_PROFILE=openai` et `OPENAI_API_KEY`.
- **Anthropic** : définissez `OPS_ASSIST_PROFILE=anthropic` et `ANTHROPIC_API_KEY`.
- **Mistral** : définissez `OPS_ASSIST_PROFILE=mistral` et `MISTRAL_API_KEY`.
- **OpenRouter** : définissez `OPS_ASSIST_PROFILE=openrouter` et `OPENROUTER_API_KEY`.

Puis lancez la même commande. Les options hébergées utilisent le réseau ; leurs tarifs et limites dépendent du fournisseur. Consultez le tableau des [fournisseurs](../../README.fr.md#fournisseurs).

Ne mettez jamais votre clé dans un fichier partagé. Les identifiants des modèles peuvent être adaptés avec `OPS_ASSIST_MODELS` ; `profile` montre le choix résolu sans afficher la clé. Avec `OPS_ASSIST_MODELS`, les variables requises par le profil ne sont pas contrôlées : configurez celles du fournisseur choisi.

## Exercices

1. Comparez les caractères et les tokens des alertes et des journaux. Un token correspond-il toujours au même nombre de caractères ? Attendez-vous à des proportions différentes selon le contenu.
2. Changez `--model` et comparez : le tokenizer commun donne ici le même compte, mais la fenêtre connue peut changer.
3. Avec un modèle, posez deux formulations de la même question. Les réponses peuvent varier : elles ne constituent pas une preuve sur l'incident.

**Sans modèle** : effectuez les deux premiers exercices et lisez les exemples de rapports dans `examples/reports/`. Aucun appel de modèle n'est nécessaire pour compter ou valider.
