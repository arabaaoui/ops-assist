# ops-assist

Un **agent d'enquête sur incident** open source, construit avec [Google ADK](https://github.com/google/adk-python).
Demandez-lui *« pourquoi l'API de paiement est-elle lente depuis 9 h ? »* : il rassemble des preuves,
puis répond par un rapport typé qui sépare les **faits** (avec leur source), les **hypothèses** (avec
un degré de confiance et les faits sur lesquels elles reposent) et ce qu'il **ne sait pas**.

**État : étapes 01 à 03.** L'agent lit les alertes et doit répondre par un `IncidentReport` valide ;
métriques, journaux et changements existent déjà dans la couche d'observation et deviennent des
outils aux étapes suivantes.

C'est le projet fil rouge d'un cours vidéo en français sur l'ingénierie des agents d'IA : chaque
chapitre lui ajoute une capacité. English version: [README.md](README.md).

## Principes

- **Lecture seule par défaut.** Une seule action d'écriture (le retour arrière d'un déploiement)
  arrive plus tard, et ne s'exécute qu'après confirmation humaine, sur le rejeu ou la pile de
  démonstration, jamais sur un environnement réel.
- **Agnostique du fournisseur.** Les modèles passent par LiteLLM ; le fournisseur est une
  configuration, avec une chaîne de repli ordonnée (`FallbackModel` d'ADK, expérimental) : le
  modèle suivant est essayé sur HTTP 429, 500, 502, 503 ou 504 avant toute sortie, jamais sur une
  requête mal formée, une erreur de connexion ou un modèle renommé.
- **Hors ligne.** Par défaut, l'agent enquête sur un incident *rejoué*, enregistré sur disque : ni
  infrastructure, ni compte. Toutes les données sont fictives.
- **Testé sans modèle.** La CI fait tourner la boucle de l'agent sur un modèle scripté : ni clé, ni coût.

## Démarrer

```bash
uv sync
uv run pytest -q                       # tout tourne hors ligne
cp .env.example .env                   # puis choisir un profil
uv run adk web apps                    # interface de développement ADK sur http://localhost:8000
```

## Fournisseurs

Choisissez un profil avec `OPS_ASSIST_PROFILE` ; `ops-assist profile` montre sa configuration et `ops-assist profile --list` les liste tous. Les exemples de `src/ops_assist/data/profiles.yaml` peuvent être remplacés via `OPS_ASSIST_PROFILES_FILE`.

| Profil | Fournisseur | Modèles | Variable à définir | Offre gratuite | Clé |
|---|---|---|---|---|---|
| `local` (défaut) | Ollama | `ollama_chat/qwen3:8b` | aucune | Local, sans frais d'API | [Ollama](https://ollama.com/) |
| `gemini` / `api` (alias) | Gemini | `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-flash-lite` | `GEMINI_API_KEY` | Oui, sous limites | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `openai` | OpenAI | `openai/gpt-4o-mini` | `OPENAI_API_KEY` | API payante | [OpenAI](https://platform.openai.com/api-keys) |
| `anthropic` | Anthropic | `anthropic/claude-haiku-4-5` | `ANTHROPIC_API_KEY` | API payante | [Anthropic](https://console.anthropic.com/settings/keys) |
| `mistral` | Mistral | `mistral/mistral-small-latest` | `MISTRAL_API_KEY` | Oui, sous limites | [Mistral](https://console.mistral.ai/api-keys/) |
| `openrouter` | OpenRouter | `openrouter/openai/gpt-4o-mini` | `OPENROUTER_API_KEY` | Ce modèle est payant | [OpenRouter](https://openrouter.ai/settings/keys) |
| `mixed` | Gemini → OpenAI → Anthropic | `gemini/gemini-2.5-flash-lite`, `openai/gpt-4o-mini`, `anthropic/claude-haiku-4-5` | `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Selon le fournisseur ; replis potentiellement payants | Voir les liens ci-dessus |

Les disponibilités et limites évoluent : vérifiez-les auprès du fournisseur. Tout fournisseur LiteLLM peut être choisi avec `OPS_ASSIST_MODELS="fournisseur/modele,fournisseur/secours"`. Cette surcharge désactive le contrôle des variables requises par le profil : configurez vous-même les identifiants du fournisseur choisi. Les modèles surchargés n'héritent pas de l'adresse du profil ; définissez `OPS_ASSIST_API_BASE` pour les serveurs compatibles OpenAI auto-hébergés comme vLLM ou LM Studio.
Des incidents enregistrés peuvent vivre hors du paquet avec `OPS_ASSIST_INCIDENTS_DIR`.

## Commandes et ateliers

```bash
uv run ops-assist profile
uv run ops-assist tokens
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist ask "Qu'est-ce que la latence ?"
uv run ops-assist investigate "Pourquoi le paiement est-il lent ?"
```

Les trois premières commandes fonctionnent sans modèle. `ask` utilise le premier modèle configuré ; `investigate` utilise la chaîne de modèles de l'agent. Les deux nécessitent un modèle local actif ou un fournisseur distant. Le comptage utilise un tokenizer fourni et reste approximatif.

Ateliers en français, de moins d'une heure : [01 — premier appel](ateliers/01-premier-appel/README.md), [02 — sortie structurée](ateliers/02-sortie-structuree/README.md), [03 — premier agent](ateliers/03-premier-agent/README.md).

## Licence

[Apache 2.0](LICENSE).

Le module 1 comprend désormais les ateliers 04 à 07 : cinq sous-systèmes, choix d'architecture, mémoire et budget de contexte (`ateliers/04-sous-systemes/` à `ateliers/07-budget-contexte/`). `uv run ops-assist triage` fonctionne hors ligne. `uv run ops-assist investigate "Pourquoi ?" --show-context` estime les tokens du prompt à chaque tour et nécessite un modèle configuré. Les résumés expurgés sont enregistrés par service affecté ; `ops-assist memory list [--service S]` et `ops-assist memory forget --service S` permettent de les consulter et de les oublier. `OPS_ASSIST_MEMORY_DIR` remplace le dossier par défaut `~/.local/state/ops-assist`. Les sessions ADK restent en mémoire par défaut. Définissez `OPS_ASSIST_SESSION_DB` avec le chemin d’un fichier SQLite pour conserver les événements et l’état hors ligne ; `--session ID` reprend ou crée une session nommée. La CLI affiche son identifiant, à réutiliser avec la même base. Cette session SQLite est distincte des résumés JSON et peut contenir des messages et résultats d’outils non expurgés ; protégez le fichier et utilisez des données fictives. Sans SQLite, un identifiant ne permet pas de reprendre une session entre deux processus CLI. L'expurgation est heuristique, sans garantie : utilisez des données fictives pour les ateliers.
