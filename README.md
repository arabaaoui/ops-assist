# ops-assist

An open-source **incident investigation agent** built with [Google ADK](https://github.com/google/adk-python).
Ask it *"why has the payment API been slow since 09:00?"*: it gathers evidence, then answers with a
typed report that separates **facts** (with their source) from **hypotheses** (with a confidence
and the facts they rest on) and from what it **does not know**.

**Status: steps 01–03.** The agent reads the alerts and must answer with a valid `IncidentReport`;
metrics, logs and changes are already in the observation layer and become tools in later steps.

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

Two model profiles, in `src/ops_assist/data/profiles.yaml` (override the file with `OPS_ASSIST_PROFILES_FILE`):

| Profile | Needs | Set |
|---|---|---|
| `local` (default) | [Ollama](https://ollama.com) and a model able to call tools | `OPS_ASSIST_PROFILE=local` |
| `api` | an API key from a provider with a free tier | `OPS_ASSIST_PROFILE=api` and the provider's key |

Model ids are examples: override them with `OPS_ASSIST_MODELS="provider/model,provider/fallback"`.
Overridden models do not inherit the profile's endpoint; set `OPS_ASSIST_API_BASE` if they need one.
Recorded incidents can live outside the package with `OPS_ASSIST_INCIDENTS_DIR`.

## CLI and workshops

```bash
uv run ops-assist profile
uv run ops-assist tokens
uv run ops-assist validate examples/reports/valid.json
uv run ops-assist ask "What is latency?"
uv run ops-assist investigate "Why is payment slow?"
```

The first three commands work without a model. `ask` calls only the first configured model; `investigate` uses the configured agent model chain. Both need a running local model or a hosted provider. Token counts use a bundled tokenizer and are approximate.

French workshops (under one hour each): [01 — first call](ateliers/01-premier-appel/README.md), [02 — structured output](ateliers/02-sortie-structuree/README.md), [03 — first agent](ateliers/03-premier-agent/README.md).

## Layout

```
src/ops_assist/
  agent.py            the agent (instruction, model, tools)
  models.py           model routing and fallback chain
  config.py           profiles and environment variables
  report.py           the typed IncidentReport
  tools.py            agent tools (read-only)
  observability/      one interface; replay source today, Prometheus and Loki connectors later
  data/               model profiles and recorded, fictional incidents (shipped in the wheel)
apps/investigator/    entry point for `adk web`
tests/                contract suite for any source, report rules, fallback chain, agent loop
                      on a scripted model, shareability scan
```

## License

[Apache 2.0](LICENSE).

Module 1 now includes workshops 04–07: five subsystems, architecture decisions, memory, and context budget (`ateliers/04-sous-systemes/` through `ateliers/07-budget-contexte/`). The deterministic `uv run ops-assist triage` works offline. `uv run ops-assist investigate "Why?" --show-context` estimates prompt tokens per model turn and requires a configured model. Reports save redacted summaries per affected service; `ops-assist memory list [--service S]` and `ops-assist memory forget --service S` inspect and delete them. Set `OPS_ASSIST_MEMORY_DIR` to change the default `~/.local/state/ops-assist`. ADK sessions are in memory by default. Set `OPS_ASSIST_SESSION_DB` to a SQLite file path to persist session events and state offline, and pass `--session ID` to resume or create a named session. The CLI prints the session ID; reuse it with the same database. The SQLite session is separate from the JSON summary store and can contain unredacted messages and tool results; use fictional data and protect the file. Without SQLite, session IDs cannot be resumed across CLI processes. Redaction is heuristic, not a guarantee; use fictional data in workshops.
