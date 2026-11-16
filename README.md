# ops-assist

An open-source **incident investigation agent** built with [Google ADK](https://github.com/google/adk-python).
Ask it *"why has the payment API been slow since 09:00?"*: it gathers evidence, then answers with a
typed report that separates **facts** (with their source) from **hypotheses** (with a confidence
and the facts they rest on) and from what it **does not know**.

**Status: step 09.** The agent investigates alerts, metrics, logs and changes through read-only tools and returns a valid `IncidentReport`.

It is the hands-on project of a French video course on AI agent engineering: every chapter adds one
capability. Version française : [README.fr.md](README.fr.md).

## Principles

- **Read-only by default.** One write action (rolling back a deployment) arrives later, and only ever
  runs after a human confirms it, against the replay or the demo stack, never a real environment.
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

Availability and free-tier limits can change; check the provider before use. Any LiteLLM provider can be selected with `OPS_ASSIST_MODELS="provider/model,provider/fallback"`. This override disables the profile's required-variable checks: configure the chosen provider's credentials yourself. Overridden models do not inherit the profile endpoint; use `OPS_ASSIST_API_BASE` for self-hosted OpenAI-compatible endpoints such as vLLM or LM Studio.
Recorded incidents can live outside the package with `OPS_ASSIST_INCIDENTS_DIR`.

## CLI and workshops

```bash
uv run ops-assist profile
uv run ops-assist mcp-serve  # MCP over stdio
uv run ops-assist tokens
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist ask "What is latency?"
uv run ops-assist investigate "Why is payment slow?"
```

The first three commands work without a model. `ask` calls only the first configured model; `investigate` uses the configured agent model chain. Both need a running local model or a hosted provider. Token counts use a bundled tokenizer and are approximate.

French workshops: [01 — first call](ateliers/01-premier-appel/README.md), [02 — structured output](ateliers/02-sortie-structuree/README.md), [03 — first agent](ateliers/03-premier-agent/README.md), [04 — subsystems](ateliers/04-sous-systemes/README.md), [05 — architecture](ateliers/05-decision-architecture/README.md), [06 — memory](ateliers/06-memoire/README.md), [07 — context budget](ateliers/07-budget-contexte/README.md), [08 — tool calls](ateliers/08-appel-d-outils/README.md), [09 — MCP](ateliers/09-mcp/README.md).

## Layout

```
src/ops_assist/
  agent.py            the agent (instruction, model, tools)
  models.py           model routing and fallback chain
  config.py           profiles and environment variables
  report.py           the typed IncidentReport
  tools.py            agent tools (read-only)
  observability/      one interface; replay, Prometheus and Loki connectors
  data/               model profiles and recorded, fictional incidents (shipped in the wheel)
apps/investigator/    entry point for `adk web`
tests/                contract suite for any source, report rules, fallback chain, agent loop
                      on a scripted model, shareability scan
```

## License

[Apache 2.0](LICENSE).

Module 1 now includes workshops 04–07: five subsystems, architecture decisions, memory, and context budget (`ateliers/04-sous-systemes/` through `ateliers/07-budget-contexte/`). The deterministic `uv run ops-assist triage` works offline. `uv run ops-assist investigate "Why?" --show-context` estimates prompt tokens per model turn and requires a configured model. Reports save redacted summaries per affected service; `ops-assist memory list [--service S]` and `ops-assist memory forget --service S` inspect and delete them. Set `OPS_ASSIST_MEMORY_DIR` to change the default `~/.local/state/ops-assist`. ADK sessions are in memory by default. Set `OPS_ASSIST_SESSION_DB` to a SQLite file path to persist session events and state offline, and pass `--session ID` to resume or create a named session. The CLI prints the session ID; reuse it with the same database. The SQLite session is separate from the JSON summary store and can contain unredacted messages and tool results; use fictional data and protect the file. Without SQLite, session IDs cannot be resumed across CLI processes. Redaction is heuristic, not a guarantee; use fictional data in workshops.

## Step 08 — tool calls and live sources

[Workshop 08 — tool calls](ateliers/08-appel-d-outils/README.md) completes step 08. Workshops 01–08 are available. The default source remains replay; `OPS_ASSIST_SOURCE=live` composes Prometheus alerts and metrics, Loki logs, and changes from an explicitly configured file for `ops-assist investigate`. Set `OPS_ASSIST_PROMETHEUS_URL` and `OPS_ASSIST_LOKI_URL`; `OPS_ASSIST_HTTP_TIMEOUT` defaults to 5 seconds and `OPS_ASSIST_TOOL_TIMEOUT` to 10 seconds. `ops-assist triage` and `tokens` remain offline replay commands. Set `OPS_ASSIST_CHANGES_FILE` to a JSON file in the recorded `changes.json` format; without it, changes are unavailable. Loki requires an indexed `level` label for level filters. The hand-made HTTP fixtures use the API formats; they are not server captures and do not exercise the time window. Timed-out workers are abandoned and do not delay process exit; the worker pool is bounded. See the workshop for labels, time window, and an offline path.

## Step 09 — MCP

`ops-assist mcp-serve` exposes the four read-only observation tools over stdio. Set `OPS_ASSIST_TOOLS=mcp` to let ADK start and consume this server; the default `inprocess` keeps direct tools. The server uses the configured source and selected incident; memory recall stays local. Injected Python sources cannot cross the process boundary. The offline [workshop](ateliers/09-mcp/README.md) demonstrates discovery and calls without a model.
