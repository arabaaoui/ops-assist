# ops-assist

An open-source **incident investigation agent** built with [Google ADK](https://github.com/google/adk-python).
Ask it *"why has the payment API been slow since 09:00?"*: it gathers evidence, then answers with a
typed report that separates **facts** (with their source) from **hypotheses** (with a confidence
and the facts they rest on) and from what it **does not know**.

**Status: step 37.** The agent investigates alerts, metrics, logs and changes through read-only tools and returns a valid `IncidentReport`.

It is the hands-on project of a French video course on AI agent engineering: almost every chapter adds one
capability, tagged `etape-NN`. Chapters 1 to 4 match steps 1 to 4; chapter 5 (the harness) has no step of
its own, so from chapter 6 on, step N belongs to chapter N+1. Version française : [README.fr.md](README.fr.md).

## Principles

- **Read-only by default.** Rollback requires explicit enablement and human confirmation. Replay changes simulated state; live connectors always refuse, and demo requires an injected client.
- **Provider-agnostic.** Models go through LiteLLM; the provider is configuration, with an ordered
  fallback chain (ADK `FallbackModel`, experimental): the next model is tried on HTTP 429, 500,
  502, 503 or 504 before any output, never on a malformed request, a connection error or a
  renamed model.
- **Runs offline.** By default the agent investigates a *replayed* incident recorded on disk: no
  infrastructure, no account. All data is fictional.
- **Tested without a model.** CI runs the agent loop on a scripted model: no key, no cost.

## Quick start

```bash
uv sync
uv run pytest -q                       # everything runs offline
cp .env.example .env                   # then pick a profile
uv run adk web apps                    # ADK developer UI on http://localhost:8000
```

## Providers

Choose a profile with `OPS_ASSIST_PROFILE`; inspect it with `ops-assist profile` or list all with `ops-assist profile --list`. The examples in `src/ops_assist/data/profiles.yaml` can be replaced using `OPS_ASSIST_PROFILES_FILE`.

| Profile | Provider | Models | Variable to set | Free tier | Key |
|---|---|---|---|---|---|
| `local` (default) | Ollama | `ollama_chat/qwen3:8b` | none | Local, no API charge | [Ollama](https://ollama.com/) |
| `gemini` / `api` (alias) | Gemini | `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-flash-lite` | `GEMINI_API_KEY` | Available subject to limits | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `openai` | OpenAI | `openai/gpt-4o-mini` | `OPENAI_API_KEY` | Paid API | [OpenAI](https://platform.openai.com/api-keys) |
| `anthropic` | Anthropic | `anthropic/claude-haiku-4-5` | `ANTHROPIC_API_KEY` | Paid API | [Anthropic](https://console.anthropic.com/settings/keys) |
| `mistral` | Mistral | `mistral/mistral-small-latest` | `MISTRAL_API_KEY` | Available subject to limits | [Mistral](https://console.mistral.ai/api-keys/) |
| `openrouter` | OpenRouter | `openrouter/openai/gpt-4o-mini` | `OPENROUTER_API_KEY` | This model is paid | [OpenRouter](https://openrouter.ai/settings/keys) |
| `mixed` | Gemini → OpenAI → Anthropic | `gemini/gemini-2.5-flash-lite`, `openai/gpt-4o-mini`, `anthropic/claude-haiku-4-5` | `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Depends on provider; fallbacks may be paid | See links above |
| `gateway` | LiteLLM proxy | `openai/ops-primary` | `OPENAI_API_KEY` | Depends on providers | proxy virtual key |
| `vertex` | Vertex AI | `vertex_ai/gemini-3.1-flash-lite` | `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`, ADC | Depends on account | ADC |
| `bedrock` | Bedrock | `bedrock/us.anthropic.claude-3-5-haiku-20241022-v1:0` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME` | Depends on account | AWS credentials |
| `azure` | Azure | `azure/gpt-4o` | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` | Depends on account | Azure key |

Availability and free-tier limits can change; check the provider before use. Any LiteLLM provider can be selected with `OPS_ASSIST_MODELS="provider/model,provider/fallback"`. This override disables the profile's required-variable checks: configure the chosen provider's credentials yourself. Overridden models do not inherit the profile endpoint; use `OPS_ASSIST_API_BASE` for self-hosted OpenAI-compatible endpoints such as vLLM or LM Studio.
Recorded incidents can live outside the package with `OPS_ASSIST_INCIDENTS_DIR`.

## CLI and workshops

`ops-assist redteam [--fast] [--json]` runs deterministic security probes offline. It exits nonzero if a probe fails; a pass is not a security proof.

`ops-assist eval list` lists the versioned incident dataset offline. `ops-assist eval run [--profile P] [--repeat N] [--show-reports] [--compare-tiers] [--gate]` evaluates replay investigations and stores results in the state directory.

```bash
uv run ops-assist eval check-reports tests/fixtures/evaluation/passing
uv run ops-assist redteam --fast  # offline security regression probes
uv run ops-assist eval cost --json
uv run ops-assist doctor --json
uv run ops-assist bench --profile local --runs 3 --prompt-file /tmp/ops-prompt.txt
uv run ops-assist profiles
uv run ops-assist profile
OPS_ASSIST_PROFILE=gateway uv run ops-assist profile
uv run ops-assist a2a-serve --port 8000
uv run ops-assist mcp-serve  # MCP over stdio; skills are available in both tool modes
uv run ops-assist tokens
uv run ops-assist tokens --all
uv run ops-assist triage
uv run ops-assist knowledge index
uv run ops-assist knowledge search "payment latency" -k 5
uv run ops-assist knowledge eval
uv run ops-assist knowledge draft-postmortem --report report.json
uv run ops-assist knowledge approve postmortem-ID
uv run ops-assist feedback --report last --up --comment "Useful"
uv run ops-assist feedback export --pairs
uv run ops-assist knowledge stale
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist ask "What is latency?"
uv run ops-assist investigate "Why is payment slow?" --show-context
```

`profile`, `a2a-serve`, `mcp-serve`, `tokens` and `validate` start without a model; an A2A investigation still requires one. `ask` calls only the first configured model; `investigate` uses the configured agent model chain. Both need a running local model or a hosted provider. Token counts use a bundled tokenizer and are approximate.

French workshops: [01 — first call](ateliers/01-premier-appel/README.md), [02 — structured output](ateliers/02-sortie-structuree/README.md), [03 — first agent](ateliers/03-premier-agent/README.md), [04 — subsystems](ateliers/04-sous-systemes/README.md), [05 — architecture](ateliers/05-decision-architecture/README.md), [06 — memory](ateliers/06-memoire/README.md), [07 — context budget](ateliers/07-budget-contexte/README.md), [08 — tool calls](ateliers/08-appel-d-outils/README.md), [09 — MCP](ateliers/09-mcp/README.md), [10 — skills](ateliers/10-skills/README.md), [11 — A2A](ateliers/11-a2a/README.md), [12 — rôles et frontières](ateliers/12-roles/README.md), [13 — security](ateliers/13-securite/README.md), [14 — gateway](ateliers/14-passerelle/README.md), [15 — embeddings](ateliers/15-embeddings/README.md), [16 — RAG](ateliers/16-rag/README.md), [17 — variantes du RAG](ateliers/17-variantes-rag/README.md), [18 — GraphRAG](ateliers/18-graphrag/README.md), [19 — RAG agentique](ateliers/19-rag-agentique/README.md), [20 — base vivante](ateliers/20-base-vivante/README.md), [21 — données](ateliers/21-donnees/README.md), [22 — Transformers](ateliers/22-transformers/README.md), [23 — changer un modèle](ateliers/23-changer-un-modele/README.md), [24 — LoRA](ateliers/24-lora/README.md), [25 — distillation](ateliers/25-distillation/README.md), [26 — renforcement](ateliers/26-renforcement/README.md), [27 — matériel](ateliers/27-materiel/README.md), [28 — CUDA](ateliers/28-cuda/README.md), [29 — inférence](ateliers/29-inference/README.md), [30 — clouds](ateliers/30-clouds/README.md), [31 — coûts](ateliers/31-couts/README.md), [32 — AIDLC](ateliers/32-aidlc/README.md), [33 — évaluations](ateliers/33-evaluations/README.md), [34 — traces](ateliers/34-traces/README.md), [35 — red team](ateliers/35-red-team/README.md), [36 — CI/CD](ateliers/36-ci-cd/README.md), [37 — failure review](ateliers/37-echecs/README.md).

## Layout

```
src/ops_assist/
  agent.py            agent, tools and expert topology
  config.py, models.py  profiles, two model tiers and fallback
  fingerprint.py      behaviour build identifier
  report.py, triage.py  report validation and preliminary triage
  evaluation.py       incident evaluation and scoring
  evals/              versioned release threshold
  cost.py             offline scripted cost comparison
  tools.py, executor.py  tools and bounded execution
  tracing.py          opt-in content-free investigation spans
  redteam.py          offline security regression probes
  security.py         permissions, confirmation and audit
  bench.py            streaming inference benchmark
  doctor.py           hardware, accelerator and optional local Ollama probes
  feedback.py         private feedback and offline preference pairs
  memory.py           incident summaries
  mcp_server.py, a2a_server.py  protocol servers
  observability/      replay, Prometheus and Loki sources
  skills/             bundled investigation methods
  knowledge/          ingestion, retrieval, evaluation, graph and approved postmortems
  data/               profiles, fictional incidents, evaluation dataset and knowledge corpus
apps/investigator/    ADK web investigator
apps/oncall_assistant/  A2A client
deploy/litellm/       gateway configuration
.github/workflows/    CI gates and image publication
Dockerfile            non-root container image
BEHAVIOR_CHANGELOG.md behaviour changes and evaluation results
docs/failure-review.md  evidence and gaps for five failure causes
ateliers/             French workshops, including cost estimation
tests/                offline contract and integration tests
```

## License

[Apache 2.0](LICENSE).

Module 1 now includes workshops 04–07: five subsystems, architecture decisions, memory, and context budget (`ateliers/04-sous-systemes/` through `ateliers/07-budget-contexte/`). The deterministic `uv run ops-assist triage` works offline. `uv run ops-assist investigate "Why?" --show-context` estimates prompt tokens per model turn and requires a configured model. Reports save redacted summaries per affected service; `ops-assist memory list [--service S]` and `ops-assist memory forget --service S` inspect and delete them. Set `OPS_ASSIST_MEMORY_DIR` to change the default `~/.local/state/ops-assist`. ADK sessions are in memory by default. Set `OPS_ASSIST_SESSION_DB` to a SQLite file path to persist session events and state offline, and pass `--session ID` to resume or create a named session. The CLI prints the session ID; reuse it with the same database. The SQLite session is separate from the JSON summary store and can contain unredacted messages and tool results; use fictional data and protect the file. Without SQLite, session IDs cannot be resumed across CLI processes. Redaction is heuristic, not a guarantee; use fictional data in workshops.

## Step 08 — tool calls and live sources

[Workshop 08 — tool calls](ateliers/08-appel-d-outils/README.md) completes step 08. Workshops 01–08 are available. The default source remains replay; `OPS_ASSIST_SOURCE=live` composes Prometheus alerts and metrics, Loki logs, and changes from an explicitly configured file for `ops-assist investigate`. Set `OPS_ASSIST_PROMETHEUS_URL` and `OPS_ASSIST_LOKI_URL`; `OPS_ASSIST_HTTP_TIMEOUT` defaults to 5 seconds and `OPS_ASSIST_TOOL_TIMEOUT` to 10 seconds. `ops-assist triage` and `tokens` remain offline replay commands. Set `OPS_ASSIST_CHANGES_FILE` to a JSON file in the recorded `changes.json` format; without it, changes are unavailable. Loki requires an indexed `level` label for level filters. The hand-made HTTP fixtures use the API formats; they are not server captures and do not exercise the time window. Timed-out workers are abandoned and do not delay process exit; the worker pool is bounded. See the workshop for labels, time window, and an offline path.

## Step 09 — MCP

`ops-assist mcp-serve` exposes the four read-only observation tools over stdio. Set `OPS_ASSIST_TOOLS=mcp` to let ADK start and consume this server; the default `inprocess` keeps direct tools. The server uses the configured source and selected incident; memory recall stays local. Injected Python sources cannot cross the process boundary. The offline [workshop](ateliers/09-mcp/README.md) demonstrates discovery and calls without a model.

## Step 10 — skills

The agent loads the bundled `latency` and `errors-5xx` skills at startup in both tool modes. ADK exposes their names and descriptions through `list_skills` and their instructions through `load_skill`; the model chooses whether to use them. No new CLI command or model provider is needed to inspect them. The [offline workshop](ateliers/10-skills/README.md) compares skills and MCP.

## Step 11 — A2A

`ops-assist a2a-serve --port 8000` serves an A2A investigator on loopback. `apps/oncall_assistant` delegates questions using ADK’s remote agent; set `OPS_ASSIST_A2A_CARD_URL` to change the card URL. The [workshop](ateliers/11-a2a/README.md) includes an in-memory offline round trip. Tasks and sessions use in-memory stores. Set `OPS_ASSIST_A2A_TOKEN` on both sides to require bearer authentication; the card remains public. `OPS_ASSIST_A2A_TIMEOUT` sets the delegation deadline in seconds (default 120). Remote access requires a TLS reverse proxy that also rewrites the loopback address advertised in the card.

## Step 12 — roles / rôles

`OPS_ASSIST_TOPOLOGY=experts uv run ops-assist investigate "Why is payment slow?" --show-context` delegates alerts and metrics to `metrics_expert`, logs and changes to `logs_expert`; the coordinator recalls memory and produces the final report. The default `single` preserves existing scripted workflows. Both topologies support in-process and MCP tools and the configured provider and fallback chain. Run `OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_roles.py` offline.

## Step 13 — security

ADK callbacks classify tools and enforce read-only by default. Writes require a human channel (the CLI prompt or ADK web UI); The A2A and MCP servers never expose a write. An agent consuming MCP observation tools can still offer confirmed rollback through the CLI or ADK web UI. `OPS_ASSIST_ALLOW_WRITES=1 uv run ops-assist investigate "Why?"` exposes rollback: the CLI displays its arguments and asks for `yes` before execution. Replay changes simulated state only; live always refuses, and demo is unavailable without an injected client. Per-invocation limits are `OPS_ASSIST_MAX_TOOL_CALLS` (100) and `OPS_ASSIST_MAX_DELEGATIONS` (10). `OPS_ASSIST_STATE_DIR` selects the private state root (default `~/.local/state/ops-assist/`); `OPS_ASSIST_AUDIT_FILE` selects a plain file name within that root (default `audit.jsonl`), never a path. A durable `pending` audit entry precedes a confirmed write; redaction is heuristic. The [workshop](ateliers/13-securite/README.md) uses scripted offline tests.

## Step 14 — gateway

The `gateway` profile points to the OpenAI-compatible proxy configured in `deploy/litellm/config.yaml`. ADK fallback logs both models; `ask` prints the reported model to stderr and `investigate` prints received model versions, or `unknown`. A proxy may return only an alias: consult its logs to identify the actual provider. [Workshop 14](ateliers/14-passerelle/README.md) covers per-key limits and an offline path.

## Step 15 — embeddings

`knowledge index` builds a local index of fictional document sections; `knowledge search` ranks them using the configured retrieval method (hybrid by default). Deterministic hashing is the offline default. `OPS_ASSIST_EMBEDDINGS` selects a LiteLLM model, `OPS_ASSIST_EMBEDDINGS_API_BASE` its endpoint, and `OPS_ASSIST_INDEX_FILE` a plain file name inside `OPS_ASSIST_STATE_DIR` (default `~/.local/state/ops-assist`). Rebuild the index after changing model or corpus. Similarity does not guarantee relevance; inspect the documents. See [workshop 15](ateliers/15-embeddings/README.md).

## Step 16 — retrieval and citations

`knowledge index` incrementally rebuilds changed documents using a checksum manifest; `knowledge search` inspects ranked sections offline with hash embeddings. The coordinator can call `search_knowledge` (up to eight bounded excerpts); experts and the MCP server do not expose it. `investigate` flags unknown chunk citations in `citation_warnings` and prints a warning. Citation existence does not establish truth or freshness. See [workshop 16](ateliers/16-rag/README.md).

## Step 17 — retrieval variants

`OPS_ASSIST_RETRIEVAL` selects `vector`, `bm25` or `hybrid` (default), combining rankings with RRF. `OPS_ASSIST_RERANKER` selects `none` (default), offline `keyword`, or a LiteLLM model; `OPS_ASSIST_RERANKER_API_BASE` sets its optional endpoint. `knowledge eval` compares recall@5 and MRR@5 using the bundled questions and hash embeddings offline. See [workshop 17](ateliers/17-variantes-rag/README.md).

## Step 18 — dependency graph

The offline `triage` includes hints for alerting direct dependencies. The coordinator can call `get_dependencies` and expand `search_knowledge` with `expand=true`; both return untrusted, bounded data. Graph edge freshness uses `OPS_ASSIST_GRAPH_MAX_AGE_DAYS` (90 days by default). See [workshop 18](ateliers/18-graphrag/README.md).

## Step 19 — agentic RAG

The coordinator chooses when to search. `investigate --show-context` displays each query and its quality or refusal. `OPS_ASSIST_MAX_SEARCHES` limits attempts per invocation (default 3). Quality is a lexical overlap heuristic, not a relevance guarantee. See [workshop 19](ateliers/19-rag-agentique/README.md) for an offline path.

## Step 20 — living knowledge

`knowledge draft-postmortem --session ID` uses the validated report saved by the CLI; without an option it uses the last report, and `--report file.json` accepts a JSON report. The redacted draft stays out of the index until `knowledge approve ID` and its confirmation. `--yes` requires `--approver`; without a terminal it also requires `OPS_ASSIST_ALLOW_NONINTERACTIVE_APPROVAL=1` and records `approval: noninteractive`. A human must decide whether to approve; the opt-in supports automation. Edited draft bodies require `--accept-edits` after review. Approval records the reviewer and time, then incrementally reindexes. `knowledge stale` and search results use `OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS` (default 90). Saved reports can contain unredacted data: protect them. See [workshop 20](ateliers/20-base-vivante/README.md).

## Step 21 — evaluation data

`ops-assist eval list` lists the offline dataset version and six fictional incidents. The manifest and datasheet are in `src/ops_assist/data/eval/`; answer keys are separate from observation tools. See [workshop 21](ateliers/21-donnees/README.md).

## Step 22 — Transformers

`ops-assist tokens --all` estimates each replay incident offline and its share of LiteLLM’s known input window. See [workshop 22](ateliers/22-transformers/README.md).

## Step 23 — changing a model

Compare profiles with `ops-assist eval run`; the literal score and its limitations are described in [workshop 23](ateliers/23-changer-un-modele/README.md).

The offline workshop dataset command `python3 ateliers/24-lora/make_dataset.py` prints fictional train/test JSON; see [workshop 24](ateliers/24-lora/README.md). It adds no ops-assist CLI command.

`OPS_ASSIST_FAST_MODELS` selects the expert fallback chain; it defaults to the main chain. When overridden, fast models do not inherit the profile endpoint; set `OPS_ASSIST_FAST_API_BASE` to specify one. Profile fast models use the main profile endpoint. `eval run --compare-tiers` compares experts on both tiers with the same coordinator, reporting pass rate, token usage and elapsed time. Unknown measurements are counted separately; failed calls may leave token totals incomplete. Evaluation requires in-process tools. Sampling variance remains even with a fixed seed. See [workshop 25](ateliers/25-distillation/README.md).

`feedback --report <file|last> --up|--down [--comment TEXT]` saves private feedback under `OPS_ASSIST_STATE_DIR`; `feedback export --pairs` prints offline JSONL. Pairs require distinct reports, the same known incident and question, and opposite net ratings: votes are summed per report, and a report with as many up as down votes is contested and left out, so a pair is never exported in both directions. The incident and question in an explicit file are trusted as given. Explicit files may wrap `report`, `incident_id` and `question`; plain reports have no pairing metadata. Redaction is heuristic and no training occurs. See [workshop 26](ateliers/26-renforcement/README.md).

`ops-assist doctor [--json]` inspects hardware offline and suggests a profile without changing configuration. The 7B estimate uses 0.6 GB per billion 4-bit weights plus 2 GB overhead, compared with free GPU memory or available RAM. Missing measurements lead to conservative advice; GPU detection is limited. See [workshop 27](ateliers/27-materiel/README.md).

## Step 28 — accelerator stack

`ops-assist doctor --ollama` optionally queries the local server at `127.0.0.1:11434` and reports loaded model CPU/GPU placement. Without this option no service is contacted. The diagnostic also detects a CUDA driver, ROCm or Metal where available; detection does not establish a complete stack. See [workshop 28](ateliers/28-cuda/README.md).

## Step 29 — inference

`bench --profile local --runs 3 --prompt-file FILE [--ollama] [--json]` measures streaming latency and throughput; remote profiles, models or endpoints require `--allow-remote`. Throughput needs output token usage returned by LiteLLM. See [workshop 29](ateliers/29-inference/README.md) for limitations and an offline path.

## Step 30 — cloud profiles

`ops-assist profiles` lists deployment locations, indicative residency and missing variables without revealing values. `vertex`, `bedrock` and `azure` provide cloud examples; see [workshop 30](ateliers/30-clouds/README.md) for credentials, regional limitations and an offline path. Vertex ADC is not checked offline. Bedrock requires explicit environment credentials; Azure requires a matching deployment name.

## Step 31 — cost and prompt caching

`ops-assist eval cost [--profile P] [--json]` compares four fictional ten-call scenarios per incident offline using LiteLLM’s bundled price map. Usage is identical across incidents and is not a measurement. Models come from the configured main and fast chains. Missing prices or cache capability are `unknown` (`null` in JSON). The scenario assumes a 4,096-token prefix per role, 150 output tokens, 6,000 initial input tokens and 200 more per call; storage and other fees are excluded. See [workshop 31](ateliers/31-couts/README.md).

`OPS_ASSIST_PROMPT_CACHE=on` (default) marks the system prefix for direct Anthropic calls; `off` removes that explicit marker. OpenAI and Gemini may apply automatic provider-side caching even when it is `off`. Investigation traces retain reported per-call token counts, with a limit and omitted-call count.

The benchmark resolves `OPS_ASSIST_API_BASE`, then `OLLAMA_API_BASE`, then localhost; only loopback endpoints are allowed without `--allow-remote`. Prompt files are limited to 64 KiB. ROCm detection reports GPU memory as unknown when it cannot be measured. Fast cloud models require their provider credentials and configuration before calls.

Cost scenarios mark a missing distinct fast tier as `n/a` (JSON `null` with a reason). Cache is simulated for direct Anthropic and automatic OpenAI/Gemini caching only; other providers include a note. Zero rates for hosted models are unknown; local Ollama is `$0 (local)`. Vertex model prices use LiteLLM’s local lookup.

## Step 32 — AIDLC

`ops-assist profile` displays the resolved configuration fingerprint; report envelopes and evaluation results retain it. See [workshop 32](ateliers/32-aidlc/README.md) and the behaviour changelog. No new configuration is required.

## Step 33 — Evaluations

`eval run --repeat N --gate` reports per-incident and overall rates and applies the versioned policy in `src/ops_assist/evals/threshold.yaml`. `eval check-reports DIR` scores saved JSON reports offline and fails if any report fails. See [workshop 33](ateliers/33-evaluations/README.md). No new configuration is required.

## Step 34 — Tracing

Install `uv sync --extra otel`, start `docker compose -f docker-compose.otel.yaml up -d`, then run `OPS_ASSIST_OTEL=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 uv run --extra otel ops-assist investigate "Why?"`. Open Jaeger at `http://127.0.0.1:16686`. Tracing is off by default; only selected metadata is exported, not message or tool content. See [workshop 34](ateliers/34-traces/README.md) for the offline path.

## Step 36 — CI/CD

Fast offline gates precede the image build; publication and OIDC signing occur only on tags. See [workshop 36](ateliers/36-ci-cd/README.md).

## Step 37 — failure review

The [failure review](docs/failure-review.md) links the need, data, validation and cost evidence and leaves ownership to assign. No CLI command or configuration is added; the [workshop](ateliers/37-echecs/README.md) includes an offline path.
