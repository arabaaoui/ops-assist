# ops-assist

Un **agent d'enquête sur incident** open source, construit avec [Google ADK](https://github.com/google/adk-python).
Demandez-lui *« pourquoi l'API de paiement est-elle lente depuis 9 h ? »* : il rassemble des preuves,
puis répond par un rapport typé qui sépare les **faits** (avec leur source), les **hypothèses** (avec
un degré de confiance et les faits sur lesquels elles reposent) et ce qu'il **ne sait pas**.

**État : étape 21.** L'agent enquête sur les alertes, métriques, journaux et changements avec des outils en lecture seule, puis produit un `IncidentReport` valide.

C'est le projet fil rouge d'un cours vidéo en français sur l'ingénierie des agents d'IA : chaque
chapitre lui ajoute une capacité. English version: [README.md](README.md).

## Principes

- **Lecture seule par défaut.** Le retour arrière exige une activation explicite et une confirmation humaine ; il agit sur l'état simulé du rejeu. Le mode réel le refuse et la démonstration exige un client injecté.
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
| `gateway` | LiteLLM proxy | `openai/ops-primary` | `OPENAI_API_KEY` | Selon les fournisseurs | clé virtuelle du proxy |

Les disponibilités et limites évoluent : vérifiez-les auprès du fournisseur. Tout fournisseur LiteLLM peut être choisi avec `OPS_ASSIST_MODELS="fournisseur/modele,fournisseur/secours"`. Cette surcharge désactive le contrôle des variables requises par le profil : configurez vous-même les identifiants du fournisseur choisi. Les modèles surchargés n'héritent pas de l'adresse du profil ; définissez `OPS_ASSIST_API_BASE` pour les serveurs compatibles OpenAI auto-hébergés comme vLLM ou LM Studio.
Des incidents enregistrés peuvent vivre hors du paquet avec `OPS_ASSIST_INCIDENTS_DIR`.

## Commandes et ateliers

`ops-assist eval list` affiche hors ligne le jeu d’incidents versionné.

```bash
uv run ops-assist profile
OPS_ASSIST_PROFILE=gateway uv run ops-assist profile
uv run ops-assist a2a-serve --port 8000
uv run ops-assist mcp-serve  # MCP sur stdio ; skills disponibles dans les deux modes
uv run ops-assist tokens
uv run ops-assist triage
uv run ops-assist knowledge index
uv run ops-assist knowledge search "payment latency" -k 5
uv run ops-assist knowledge eval
uv run ops-assist knowledge draft-postmortem --report report.json
uv run ops-assist knowledge approve postmortem-ID
uv run ops-assist knowledge stale
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist ask "Qu'est-ce que la latence ?"
uv run ops-assist investigate "Pourquoi le paiement est-il lent ?" --show-context
```

`profile`, `a2a-serve`, `mcp-serve`, `tokens` et `validate` démarrent sans modèle ; une enquête A2A en nécessite toutefois un. `ask` utilise le premier modèle configuré ; `investigate` utilise la chaîne de modèles de l'agent. Les deux nécessitent un modèle local actif ou un fournisseur distant. Le comptage utilise un tokenizer fourni et reste approximatif.

Ateliers en français : [01 — premier appel](ateliers/01-premier-appel/README.md), [02 — sortie structurée](ateliers/02-sortie-structuree/README.md), [03 — premier agent](ateliers/03-premier-agent/README.md), [04 — sous-systèmes](ateliers/04-sous-systemes/README.md), [05 — architecture](ateliers/05-decision-architecture/README.md), [06 — mémoire](ateliers/06-memoire/README.md), [07 — budget de contexte](ateliers/07-budget-contexte/README.md), [08 — appel d’outils](ateliers/08-appel-d-outils/README.md), [09 — MCP](ateliers/09-mcp/README.md), [10 — skills](ateliers/10-skills/README.md), [11 — A2A](ateliers/11-a2a/README.md), [12 — rôles et frontières](ateliers/12-roles/README.md), [13 — sécurité](ateliers/13-securite/README.md), [14 — passerelle](ateliers/14-passerelle/README.md), [15 — embeddings](ateliers/15-embeddings/README.md), [16 — RAG](ateliers/16-rag/README.md), [17 — variantes du RAG](ateliers/17-variantes-rag/README.md), [18 — GraphRAG](ateliers/18-graphrag/README.md), [19 — RAG agentique](ateliers/19-rag-agentique/README.md), [20 — base vivante](ateliers/20-base-vivante/README.md), [21 — données](ateliers/21-donnees/README.md).

## Organisation

```
src/ops_assist/
  agent.py            agent, tools and expert topology
  config.py, models.py  profiles, routing and fallback
  report.py, triage.py  report validation and preliminary triage
  tools.py, executor.py  tools and bounded execution
  security.py         permissions, confirmation and audit
  memory.py           incident summaries
  mcp_server.py, a2a_server.py  protocol servers
  observability/      replay, Prometheus and Loki sources
  skills/             bundled investigation methods
  knowledge/          ingestion, retrieval, evaluation, graph and approved postmortems
  data/               profiles, fictional incidents, evaluation dataset and knowledge corpus
apps/investigator/    ADK web investigator
apps/oncall_assistant/  A2A client
deploy/litellm/       gateway configuration
ateliers/             ateliers en français, dont l’architecture des données
tests/                offline contract and integration tests
```

## Licence

[Apache 2.0](LICENSE).

Le module 1 comprend désormais les ateliers 04 à 07 : cinq sous-systèmes, choix d'architecture, mémoire et budget de contexte (`ateliers/04-sous-systemes/` à `ateliers/07-budget-contexte/`). `uv run ops-assist triage` fonctionne hors ligne. `uv run ops-assist investigate "Pourquoi ?" --show-context` estime les tokens du prompt à chaque tour et nécessite un modèle configuré. Les résumés expurgés sont enregistrés par service affecté ; `ops-assist memory list [--service S]` et `ops-assist memory forget --service S` permettent de les consulter et de les oublier. `OPS_ASSIST_MEMORY_DIR` remplace le dossier par défaut `~/.local/state/ops-assist`. Les sessions ADK restent en mémoire par défaut. Définissez `OPS_ASSIST_SESSION_DB` avec le chemin d’un fichier SQLite pour conserver les événements et l’état hors ligne ; `--session ID` reprend ou crée une session nommée. La CLI affiche son identifiant, à réutiliser avec la même base. Cette session SQLite est distincte des résumés JSON et peut contenir des messages et résultats d’outils non expurgés ; protégez le fichier et utilisez des données fictives. Sans SQLite, un identifiant ne permet pas de reprendre une session entre deux processus CLI. L'expurgation est heuristique, sans garantie : utilisez des données fictives pour les ateliers.

## Étape 08 — appels d’outils et sources réelles

[L’atelier 08 — appel d’outils](ateliers/08-appel-d-outils/README.md) termine l’étape 08 ; les ateliers 01 à 08 sont disponibles. Le rejeu reste la source par défaut. Pour `ops-assist investigate`, `OPS_ASSIST_SOURCE=live` associe alertes et métriques Prometheus, journaux Loki et changements issus d’un fichier explicitement configuré. Définissez `OPS_ASSIST_PROMETHEUS_URL` et `OPS_ASSIST_LOKI_URL` ; `OPS_ASSIST_HTTP_TIMEOUT` vaut 5 secondes et `OPS_ASSIST_TOOL_TIMEOUT` 10 secondes par défaut. `ops-assist triage` et `tokens` restent des commandes de rejeu hors ligne. Définissez `OPS_ASSIST_CHANGES_FILE` vers un fichier JSON au format `changes.json` ; sans lui, les changements sont indisponibles. Le filtrage de niveau Loki exige un label `level` indexé. Les fixtures HTTP sont fabriquées à la main aux formats des API : elles ne proviennent pas d’un serveur et ne vérifient pas la fenêtre temporelle. Les threads expirés sont abandonnés sans retarder la sortie ; leur pool est limité. L’atelier précise les labels, la fenêtre et le parcours hors ligne.

## Étape 09 — MCP

`ops-assist mcp-serve` expose les quatre outils d’observation en lecture seule sur stdio. Définissez `OPS_ASSIST_TOOLS=mcp` pour qu’ADK lance et utilise ce serveur ; `inprocess` reste le mode par défaut. Le serveur utilise la source configurée et l’incident sélectionné ; le rappel de mémoire reste local. Une source Python injectée ne traverse pas la frontière de processus. L’[atelier hors ligne](ateliers/09-mcp/README.md) montre la découverte et les appels sans modèle.

## Étape 10 — skills

L’agent charge les skills intégrés `latency` et `errors-5xx` au démarrage dans les deux modes d’outils. ADK expose leurs noms et descriptions avec `list_skills` et leurs instructions avec `load_skill` ; le modèle choisit de les utiliser ou non. Aucune nouvelle commande CLI ni aucun fournisseur ne sont nécessaires pour les consulter. L’[atelier hors ligne](ateliers/10-skills/README.md) compare skills et MCP.

## Étape 11 — A2A

`ops-assist a2a-serve --port 8000` expose l’enquêteur A2A sur l’interface locale. `apps/oncall_assistant` délègue les questions via l’agent distant ADK ; `OPS_ASSIST_A2A_CARD_URL` permet de changer l’adresse de la carte. L’[atelier](ateliers/11-a2a/README.md) propose un échange hors ligne en mémoire. Les tâches et sessions sont en mémoire. Définissez `OPS_ASSIST_A2A_TOKEN` des deux côtés pour exiger une authentification bearer ; la carte reste publique. `OPS_ASSIST_A2A_TIMEOUT` fixe le délai de délégation en secondes (120 par défaut). Un accès distant nécessite un reverse proxy TLS qui adapte aussi l’adresse locale annoncée dans la carte.

## Étape 12 — rôles et frontières

`OPS_ASSIST_TOPOLOGY=experts uv run ops-assist investigate "Pourquoi le paiement est-il lent ?"` délègue alertes et métriques à `metrics_expert`, journaux et changements à `logs_expert` ; le coordinateur rappelle la mémoire et produit le rapport final. Le défaut `single` préserve les scénarios scriptés existants. Les deux topologies prennent en charge les outils en processus ou MCP et le profil et sa chaîne de repli. Pour tester hors ligne : `OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_roles.py`.

## Étape 13 — sécurité

Les callbacks ADK classent les outils et imposent la lecture seule par défaut. Les écritures exigent un canal humain (confirmation dans la CLI ou l’interface ADK web) ; les serveurs A2A et MCP n’exposent jamais d’écriture. Un agent qui consulte des outils MCP peut toujours proposer le retour arrière confirmé dans la CLI ou l’interface ADK web. `OPS_ASSIST_ALLOW_WRITES=1 uv run ops-assist investigate "Pourquoi ?"` expose le retour arrière : la CLI affiche ses arguments et demande `yes` avant l'exécution. Le rejeu modifie uniquement un état simulé ; le mode réel refuse toujours, et la démonstration est indisponible sans client injecté. Les plafonds par invocation sont `OPS_ASSIST_MAX_TOOL_CALLS` (100) et `OPS_ASSIST_MAX_DELEGATIONS` (10). `OPS_ASSIST_STATE_DIR` choisit la racine privée (par défaut `~/.local/state/ops-assist/`) ; `OPS_ASSIST_AUDIT_FILE` choisit un simple nom de fichier dans cette racine (par défaut `audit.jsonl`), jamais un chemin. Une entrée `pending` durable précède toute écriture confirmée ; l'expurgation est heuristique. Sans modèle, l'[atelier 13](ateliers/13-securite/README.md) utilise les tests scriptés.

## Étape 14 — passerelle

Le profil `gateway` dirige les appels vers le proxy compatible OpenAI configuré dans `deploy/litellm/config.yaml`. Le repli ADK émet un avertissement avec les deux modèles ; `ask` affiche le modèle déclaré sur stderr et `investigate` affiche les versions reçues, ou `unknown`. Un proxy peut ne renvoyer qu’un alias : consultez ses traces pour identifier le fournisseur effectif. L’[atelier 14](ateliers/14-passerelle/README.md) décrit les quotas par clé et un parcours hors ligne.

## Étape 15 — embeddings

La commande `knowledge index` construit un index local des sections du corpus fictif ; `knowledge search` les classe selon la méthode configurée (hybride par défaut). Le hachage déterministe est le défaut hors ligne. `OPS_ASSIST_EMBEDDINGS` sélectionne un modèle LiteLLM et `OPS_ASSIST_EMBEDDINGS_API_BASE` son serveur ; `OPS_ASSIST_INDEX_FILE` choisit un nom de fichier simple dans `OPS_ASSIST_STATE_DIR` (par défaut `~/.local/state/ops-assist`). Reconstruisez l’index après un changement de modèle ou de corpus. La similarité ne garantit pas la pertinence ; consultez les documents. Voir l’[atelier 15](ateliers/15-embeddings/README.md).

## Étape 16 — recherche et citations

`knowledge index` réindexe les documents modifiés grâce à un manifeste de checksums ; `knowledge search` classe les sections hors ligne avec le hachage. Le coordinateur dispose de `search_knowledge` (huit extraits bornés au maximum), absent des experts et du serveur MCP. `investigate` signale les citations inconnues dans `citation_warnings` et affiche un avertissement. Une citation existante ne garantit ni vérité ni fraîcheur. Voir l’[atelier 16](ateliers/16-rag/README.md).

## Étape 17 — variantes de recherche

`OPS_ASSIST_RETRIEVAL` choisit `vector`, `bm25` ou `hybrid` (défaut), qui fusionne les rangs par RRF. `OPS_ASSIST_RERANKER` choisit `none` (défaut), `keyword` hors ligne ou un modèle LiteLLM ; `OPS_ASSIST_RERANKER_API_BASE` définit son serveur facultatif. `knowledge eval` compare rappel@5 et MRR@5 sur les questions fournies avec le hachage hors ligne. Voir l’[atelier 17](ateliers/17-variantes-rag/README.md).

## Étape 18 — graphe de dépendances

La commande hors ligne `triage` inclut des indices pour les dépendances directes en alerte. Le coordinateur dispose de `get_dependencies` et de `search_knowledge` avec `expand=true` ; leurs résultats sont bornés et non fiables. `OPS_ASSIST_GRAPH_MAX_AGE_DAYS` fixe le seuil de péremption des relations (90 jours par défaut). Voir l’[atelier 18](ateliers/18-graphrag/README.md).

## Étape 19 — RAG agentique

Le coordinateur choisit quand chercher. `investigate --show-context` affiche chaque requête et sa qualité ou son refus. `OPS_ASSIST_MAX_SEARCHES` limite les tentatives par invocation (3 par défaut). La qualité est une heuristique lexicale, pas une garantie de pertinence. Voir l’[atelier 19](ateliers/19-rag-agentique/README.md) pour un parcours hors ligne.

## Étape 20 — base vivante

`knowledge draft-postmortem --session ID` utilise le rapport validé enregistré par la CLI ; sans option il utilise le dernier, et `--report fichier.json` accepte un rapport JSON. Le brouillon expurgé reste hors index jusqu’à `knowledge approve ID` et sa confirmation. `--yes` exige `--approver` ; hors terminal, il exige aussi `OPS_ASSIST_ALLOW_NONINTERACTIVE_APPROVAL=1` et inscrit `approval: noninteractive`. Un humain doit décider de la validation ; cette option permet une automatisation explicite. Après modification du corps, sa relecture et `--accept-edits` sont nécessaires. L’approbation inscrit auteur et date, puis réindexe les documents modifiés. `knowledge stale` et les résultats de recherche utilisent `OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS` (90 par défaut). Les rapports enregistrés peuvent contenir des données non expurgées : protégez-les. Voir l’[atelier 20](ateliers/20-base-vivante/README.md).

## Étape 21 — données d’évaluation

`ops-assist eval list` affiche hors ligne la version et les six incidents fictifs du jeu. Le manifeste et la datasheet sont dans `src/ops_assist/data/eval/` ; les corrigés restent séparés des outils. Voir l’[atelier 21](ateliers/21-donnees/README.md).
