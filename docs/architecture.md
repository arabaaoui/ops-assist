# Five subsystems in ops-assist

An investigation starts with observations and ends with a validated report. The pre-triage is deterministic; the agent remains responsible for investigating the evidence.

```mermaid
flowchart LR
    P[Perception] --> R[Reasoning and planning]
    R --> A[Action: read tools]
    A --> P
    R --> C[Communication: report]
    C --> L[Learning: stored summaries]
    L --> A
```

## Perception

The observation interface and replay source live in `src/ops_assist/observability/base.py` and `src/ops_assist/observability/replay.py`. ADK invokes tools that obtain observations; it does not supply this incident source. Prometheus supplies alerts and metrics, Loki supplies logs, and the composite source uses an explicitly configured changes file; without it, changes are unavailable. Streaming alerts remain future work.

## Reasoning and planning

The deterministic pre-triage in `src/ops_assist/triage.py` selects candidates, while `src/ops_assist/agent.py`, `src/ops_assist/models.py` and `src/ops_assist/prompts/investigator.md` configure the model and instruction. ADK runs the model and its tool loop; planning is implicit in model choices, not a guaranteed plan. Explicit planning is future work; incident evaluation is described below.

## Action

Read-only tools in `src/ops_assist/tools.py` retrieve evidence and bounded summaries. ADK exposes their schemas and dispatches calls. An explicitly enabled rollback requires ADK human confirmation, changes replay state only, and refuses live connectors.

## Learning

`src/ops_assist/memory.py` stores validated report summaries and supports recall; `src/ops_assist/run.py` uses ADK in-memory sessions by default or SQLite sessions when `OPS_ASSIST_SESSION_DB` is set. SQLite persists session events and state and permits resuming a session by ID; it is separate from long-term summaries. ADK provides both session services. This is retrieval, not model learning: automated feedback and adaptation remain future work.

## Communication

`src/ops_assist/report.py` defines the report; `src/ops_assist/cli.py` prints it and the trace. ADK validates the output schema and stores the output in session state. A2A adds agent-to-agent communication; richer interfaces remain future work.

## Tool calls and live sources

`OPS_ASSIST_SOURCE` selects replay by default or a composite of Prometheus, Loki and an optional explicit changes file. Both live connectors reject changes directly. Prometheus requests the last hour and requires a single series; Loki uses indexed `service` and `level` labels, filters level server-side, and checks service label values to distinguish a silent service from an unknown one. The HTTP timeout defaults to five seconds. The async tools run synchronous source operations in a dedicated pool of four daemon workers and four queued tasks with a ten-second default timeout; a timed-out thread is abandoned and does not delay process exit. Hand-made HTTP fixtures in the API formats exercise the same declared-capability contract without network access; they are not server captures and do not exercise the time window.

## MCP over stdio

`OPS_ASSIST_TOOLS=mcp` replaces the four in-process observation functions with an ADK `McpToolset` connected to a local child process. The official MCP SDK server registers the same functions and source configuration; the selected incident is passed to the child. Discovery and calls use stdio, and the runner closes the toolset after an investigation. Memory recall and deterministic pre-triage remain in the agent process. Arbitrary injected Python sources cannot be transferred and are rejected in MCP mode. The default `inprocess` mode and model profiles are unchanged. MCP SDK 2 names the former `FastMCP` server class `MCPServer`.

## Investigation skills

At agent construction, ADK loads and validates the packaged `latency` and `errors-5xx` SKILL.md files. The agent registers them with `SkillToolset` in both direct and MCP modes. ADK exposes discovery through `list_skills` and returns the selected instructions through `load_skill`; using these instructions remains a model decision. Skills describe investigation methods and do not provide observation data or replace the read-only tools. Invalid files fail startup with their path.

## A2A delegation

`src/ops_assist/a2a_server.py` publishes the configured investigator through ADK `to_a2a` and an explicit card advertising the `investigate` skill. The CLI binds the server to loopback. `apps/oncall_assistant` uses a custom ADK agent containing `RemoteA2aAgent` to forward the question and validate the returned `IncidentReport` before presenting it. The remote investigator retains its configured model profile, source and tool mode. A2A delegates an investigation; MCP exposes individual observation tools and can be used inside that investigation. ADK keeps tasks and sessions in memory by default; an optional `OPS_ASSIST_A2A_TOKEN` enforces bearer authentication on A2A calls while leaving the card public. `OPS_ASSIST_A2A_TIMEOUT` bounds delegation to 120 seconds by default. For remote access, deploy a TLS reverse proxy in front of the loopback listener and rewrite the loopback URL advertised in the card. The offline test uses ASGI transport and a scripted model to exercise the card, remote request and sourced response without a network or real model.

## Étape 12 : rôles et frontières

La topologie `single` reste le défaut pour préserver les scénarios existants. Avec `OPS_ASSIST_TOPOLOGY=experts`, le coordinateur conserve le pré-triage, le rappel mémoire, les skills et le rapport final ; deux sous-agents `single_turn` déclarés dans `sub_agents` et exposés comme outils par ADK collectent les preuves : `metrics_expert` possède `get_metric` et `get_alerts`, et `logs_expert` possède `get_logs` et `get_changes`. Les experts ne se voient pas et ne transfèrent pas le contrôle. En mode MCP, deux filtres distincts limitent les outils découverts par chaque expert. Tous utilisent le profil et la chaîne de repli configurés. Les résultats restent des données non fiables ; le coordinateur valide le rapport structuré. Cette délégation ajoute des appels de modèle et peut perdre des détails dans les synthèses. Les anciennes versions utilisaient directement `AgentTool` pour envelopper un agent. ADK 2.14.1 déconseille cet usage direct : il crée un runner et une session imbriqués, tandis que `single_turn` exécute le sous-agent dans la session du parent et rend ses événements visibles dans cette session.

## Security boundary

`src/ops_assist/security.py` attaches the same before, after and error callbacks to the coordinator and experts. Its explicit tool table defaults unknown tools to write; read-only is the default. `OPS_ASSIST_ALLOW_WRITES=1` exposes a confirmation-gated `FunctionTool` for rollback. ADK interrupts the call and the CLI relays the human response. The replay action verifies the deployment and writes an atomic simulated state file outside the recorded incident; live always refuses, while demo requires an injected client and has no offline implementation. Per-invocation budgets count tool calls and expert delegations across agents; ADK reuses the invocation ID when confirmation resumes, so the same counter applies. Counters are in memory, not a persistent quota. Audit JSONL records outcomes, durations and heuristically redacted arguments, including refusals. A confirmed write requires a flushed and synchronized pending entry before execution; later audit writes can still fail. The audit and state files use plain names inside one directory opened through a validated directory descriptor, which anchors all file operations. The root must be owned by the current user, not group or world writable, not overlap the package and contain no symlink components. Files must be owned regular files without symlinks or hard links; audit permissions are enforced as 0600. The A2A and MCP servers never expose a write. An agent consuming MCP tools may still offer confirmed rollback through a human channel such as the CLI or ADK web UI. The direct MCP server exposes only read tools and does not use the agent callbacks for independent clients. Pre-triage is deterministic source access, not an ADK tool call. The offline security tests exercise the trapped log, confirmation, three source modes and budget decisions.

## AI gateway

The `gateway` profile sends an OpenAI-compatible request to the local LiteLLM proxy. `deploy/litellm/config.yaml` routes a Gemini alias to an OpenAI fallback and disables message logging in LiteLLM callbacks. A PostgreSQL-backed virtual key, created separately with the documented budget and rate limits, controls client access and enables spend records. Provider keys remain in the proxy environment. ADK fallback is independent: its client-side transitions log both model names before the next attempt. The CLI reports model versions supplied by responses; a proxy may return only an alias, so its internal fallback cannot be inferred reliably from the CLI alone. Provider and infrastructure logs require their own confidentiality controls. The offline tests exercise ADK fallback with fake clients, not the proxy.

## Knowledge search

The CLI builds a flat local JSON index from sections of the packaged fictional Markdown corpus. Hashing gives a deterministic offline baseline; a configurable LiteLLM embedding model can instead produce normalized vectors. The index is stored atomically within the validated state root; `OPS_ASSIST_INDEX_FILE` is a plain file name. It records the embedding identity and dimension and refuses incompatible queries. Vector search ranks cosine similarity across all sections; the configurable default also combines lexical rankings as described below. Retrieved text is untrusted data and similarity is not evidence of relevance. The coordinator also has the read-only `search_knowledge` tool; MCP does not expose it. Rebuild the index whenever its corpus or embedding model changes.

## Recherche documentaire et citations

Le pipeline charge les documents fictifs, découpe leurs sections, calcule les embeddings puis construit un index cosinus local. Un manifeste enregistre l’identifiant, le checksum et le nombre de sections de chaque document ; seuls les documents modifiés sont réencodés dans le même espace vectoriel. Le changement de modèle reconstruit l’index. Le coordinateur seul dispose de `search_knowledge`, classé en lecture et limité à huit extraits de 800 caractères ; MCP ne l’expose pas. Les résultats restent des données non fiables. Après génération, `investigate` contrôle les identifiants de chunks cités contre l’index et inscrit les avertissements dans le rapport et la trace. Ce contrôle ne démontre ni la fraîcheur ni la fidélité des affirmations ; les procédures restent des conseils et ne constituent pas des observations de l’incident.

## Retrieval variants

The lexical BM25 index is built in memory from the same persisted chunks as the vector index. `OPS_ASSIST_RETRIEVAL` selects vector, BM25 or hybrid rankings; hybrid uses reciprocal rank fusion with constant 60. Optional keyword overlap or a configurable LiteLLM model reranks up to 20 candidates by default, preserving retrieval scores in output. The model scores each untrusted excerpt separately and must return a single digit from 0 to 3. On an invalid score or provider error, search retains the original ranking, logs a warning and reports a sanitized reranking failure in the tool result. `knowledge eval` builds a separate hash index in memory and measures mean recall@5 and MRR@5 against ten packaged fictional questions; it does not access a provider or alter the persisted index. These metrics describe the labeled set, not production quality.

## Dependency graph and GraphRAG-lite

The packaged fictional graph represents directed calls, dependencies and ownership with dated edges. `get_dependencies` traverses up to three hops in either direction, returns provenance and marks edges older than `OPS_ASSIST_GRAPH_MAX_AGE_DAYS` (90 by default). Pretriage adds bounded hints when a directly dependent service is also alerting; these are leads, not diagnoses. Optional `search_knowledge(expand=true)` matches service names in the query and adds bounded corpus excerpts for direct technical dependencies, with the edges that led to them. This local expansion is not community-based GraphRAG. Graph data and excerpts are untrusted; stale flags do not prove correctness. Both tools remain coordinator-only reads, including when observations use MCP.

## Agentic retrieval

The coordinator decides whether knowledge search helps, reformulates weak searches at most twice by instruction, and records an unknown when it stops. The security boundary enforces `OPS_ASSIST_MAX_SEARCHES` (three attempts per invocation by default), independently of the general tool budget; a refusal returns `knowledge_search_limit`. The trace associates each query with its tool response by call ID, including failures and refusals; an unmatched response leaves the outcome unknown. Tool arguments are redacted and bounded, and the trace retains at most 50 calls plus an omitted count. Counters are in memory and do not survive a process restart.

Quality is a heuristic computed on the returned primary chunks before graph expansion: the maximum fraction of distinct query tokens present in the first 800 characters of any returned chunk. No chunks gives `none`; an overlap of at least 0.5 gives `good`; otherwise it is `weak` with a reformulation suggestion. This normalized lexical score is independent of the incompatible vector, BM25 and RRF score scales and remains only a signal, not proof of relevance.

## Living knowledge

The CLI saves each validated investigation report by session and as the latest report in the local state directory. Draft generation validates that report, records a SHA-256 hash of its canonical JSON and session provenance, and applies the memory redactor before writing Markdown. Reports themselves may contain unredacted data and require protection.

Drafts are excluded from retrieval. Approval records the supplied reviewer, UTC time and interactive or explicitly opted-in noninteractive mode, moves the document to the approved local corpus and incrementally rebuilds the existing index. Changed draft bodies require explicit acceptance; the approved body is redacted again and marked as untrusted. Failed indexing leaves the draft available. Search results carry the document date and a stale flag and reason calculated at query time against UTC; `OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS` controls the threshold. These results remain untrusted data, and freshness does not establish correctness.

## Incident evaluation data

The versioned offline manifest in `data/eval/` lists six fictional replay cases and their questions. Its checksum covers each question and all six recording files, including the answer key; published version checksums are checked against the packaged `data/eval/published.yaml` registry at load time and historical entries are pinned in tests. The datasheet records provenance, intended use and limitations. Replay reads only the five observation files, rejecting symbolic links and answer keys; token counting uses the same allowlist. Evaluation answers are kept outside the knowledge corpus, prompts, skills and examples, with an exact-text regression guard. This guard cannot detect paraphrases, and the public dataset is not a secret benchmark. Four cases accept causal links as hypotheses without requiring an unproven conclusion; the answer keys define accepted statuses and hypotheses for the scoring engine below. Evaluation introduces no new agent tool.

The offline `tokens --all` command enumerates the configured replay directory and counts only observation files with LiteLLM’s bundled tokenizer. Each incident is compared separately with the selected model’s `max_input_tokens` metadata when available; the estimate excludes instructions, tool schemas, history and output and may differ from the server’s actual limit.

## Incident evaluation

`ops-assist eval run` loads the validated versioned dataset, runs each question with its bundled replay source and a fresh in-memory session, and scores the report against the separate answer key. Status, report validity and required fact source categories are checked. For a known root cause, the highest-confidence hypothesis must contain both expected identifiers in one affirmative sentence. For `hypotheses_only`, at least one hypothesis must contain the service and change from an accepted entry in one affirmative sentence. For `insufficient_data`, unknowns must be nonempty and no hypothesis may have confidence above 0.5. A status mismatch always fails.

Sentence-level English negation markers include `not`, `no`, `ruled out`, `excluded`, `unlikely`, `rather than` and `instead of`. A marker anywhere in a sentence makes that sentence non-affirmative; this conservative heuristic does not understand scope, double negation, synonyms or causal meaning. Forbidden conclusions are checked in summary and hypotheses, sentence by sentence, with case folding and a small set of simple inflections; paraphrases and intervening words can evade the check. Neither cited sources nor identifier mentions prove the evidence or causal link. Review reports as well as scores.

Failures and investigation errors remain in the denominator. Evaluation disables tool writes and does not append investigation summaries, but existing memory and retrieval configuration can affect a run; keep them fixed for comparisons. The private result file in the confined state directory contains the dataset checksum, profile, model IDs, per-case checks, validated reports and bounded errors. Reports and errors receive heuristic secret redaction, which cannot guarantee removal of all sensitive content. `--show-reports` prints those same redacted reports and errors. See [decision 0002](decisions/0002-no-fine-tuning.md) and [workshop 23](../ateliers/23-changer-un-modele/README.md).

## LoRA workshop dataset

The offline workshop generator reads the bundled fictional replay alerts and applies distinct templates to produce deterministic train and test JSON with five alert categories. The same source alerts appear in both partitions, so the held-out texts assess reformulation rather than generalization to unseen incidents; the dataset is illustrative and no model is trained or called. This adds no agent tools, dependencies, environment variables or CLI commands. See [workshop 24](../ateliers/24-lora/README.md).

## Expert model tiers

The coordinator always uses the main model chain. Experts use `fast_models` from the profile or `OPS_ASSIST_FAST_MODELS`; without either, they use the resolved main chain. An explicit `OPS_ASSIST_MODELS` override also becomes the default expert chain. Both tiers use the same configured endpoint and LiteLLM fallback routing. `eval run --compare-tiers` forces the expert topology and evaluates the dataset twice in fresh sessions, alternating main and fast experts for each incident and repetition. It requests temperature zero and a fixed seed, with unsupported LiteLLM parameters dropped; providers may ignore the seed, so sampling variance remains. Evaluation rejects MCP mode before starting and uses in-process replay. Known fast-tier providers are checked for their required API keys before CLI execution. It records pass rate, elapsed time, total tokens and the number of calls estimated from serialized requests and responses when usage metadata is absent. Calls whose token count cannot be measured are counted separately as unknown. Failed calls without a completed investigation can be missing from token totals. The comparison does not train a model; see [workshop 25](../ateliers/25-distillation/README.md).

## Feedback and preference pairs

The CLI stores validated, redacted feedback as private files in the confined state directory. The report hash identifies the canonical validated report before redaction. For CLI investigations, the stored report includes the incident and original question; explicit inputs can provide the same metadata in an envelope. Export pairs only distinct reports with opposite ratings for the same known incident and question, as JSONL on standard output. Redaction is heuristic, feedback is untrusted, and export performs no training or model call.

## Offline hardware diagnosis

`doctor` runs independently of model settings and agent tools. Linux probes read `/proc/cpuinfo` and `/proc/meminfo`; macOS uses bounded `sysctl` queries and identifies Apple Silicon as unified memory. Where available, bounded `nvidia-smi` queries report one GPU and its free memory. The command cannot discover every GPU type; macOS available memory is unknown. Probe errors are reported as unknown. Advice compares a 7B model at 0.6 GB per billion 4-bit weights plus 2 GB overhead against measured available memory; unknown or insufficient capacity recommends an API profile. The estimate is advisory, does not change settings and does not guarantee performance or fit. No agent tool, dependency, network call or environment variable is added. See [workshop 27](../ateliers/27-materiel/README.md).

## Accelerator stack

The doctor command detects the NVIDIA driver through a bounded `nvidia-smi` query, ROCm through `rocm-smi`, or Metal on Apple Silicon. This identifies available tools or hardware, not a complete compatible runtime stack. The optional `--ollama` probe queries only `127.0.0.1:11434/api/ps` with a two-second timeout, no redirects and a bounded response; it reports CPU, GPU or mixed placement from `size_vram` and `size`. It is disabled by default, independent of profile settings, and failures become unknown. The endpoint and process probes are injectable in tests. No model call, agent tool, dependency or environment variable is added. See [workshop 28](../ateliers/28-cuda/README.md).

## Inference benchmark

`bench` performs sequential streamed LiteLLM completions using the first configured model. It measures time to first visible text, total time, and approximate decode throughput from completion token usage returned by LiteLLM and the interval between first and last text chunks. Chunk boundaries and reasoning tokens can affect the estimate; missing usage or a zero interval makes throughput unavailable. Median, minimum, maximum and sample count are reported. Runs, prompt size and output tokens are bounded; the optional fixed-loopback Ollama probe reuses the doctor parser. Remote profiles, non-Ollama model overrides and non-loopback endpoints require explicit `--allow-remote`. The command adds no agent tool or environment variable. See [workshop 29](../ateliers/29-inference/README.md).

## Cloud deployment profiles

The bundled Vertex, Bedrock and Azure profiles use LiteLLM model identifiers and declare required environment variables. The CLI checks these before model calls, including benchmarks; explicit model overrides retain their existing bypass. `profiles` shows execution location, indicative residency and missing variable names only. ADC availability is not probed offline. Bedrock uses explicit environment credentials and its example inference profile may route across regions. Azure requires a deployment name matching the model ID. Provider contracts and configuration determine actual residency. See [workshop 30](../ateliers/30-clouds/README.md).

## Cost scenarios and prompt caching

Every LiteLLM call is tagged with agent or task name, profile and package version. Investigation traces retain reported input, cached input and output tokens for each response, bounded to 50 entries with an omission counter. Missing cache usage remains unknown. LiteLLM metadata supports attribution inside LiteLLM and is not a promise that each upstream provider stores those fields.

ADK constructs a system message before conversation messages and passes tool declarations separately; a scripted two-turn investigation checks that both serialized components remain byte-identical. `OPS_ASSIST_PROMPT_CACHE=on` (the default) asks LiteLLM to place an ephemeral cache breakpoint on the system message for direct Anthropic models. `off` removes this explicit breakpoint. OpenAI automatic and Gemini implicit caching are provider-controlled, so `off` cannot guarantee that they are disabled. Actual cache eligibility depends on model, minimum prefix length and provider behavior.

`ops-assist eval cost` makes no model call. It applies the bundled local LiteLLM price map to the same fictional ten-call scenario for each case in the evaluation manifest. The coordinator makes six calls and each expert makes two; the first input has 6,000 tokens and grows by 200 per call, each output has 150 tokens, and each role has a hypothetical 4,096-token stable prefix. Four scenarios compare a cache hit after each role's first call with no hit and main-only experts with configured fast experts. Input includes cache read and creation tokens; a creation charge is included when present in the map. Storage, other fees, token-count changes and model quality are outside this estimate. Missing prices or cache support are unknown, never zero. These are counterfactuals, not measured investigations or provider bills; see [workshop 31](../ateliers/31-couts/README.md).

## Behaviour fingerprint

`ops-assist profile`, saved report envelopes and evaluation results identify the resolved behaviour with a 16-hex SHA-256 prefix. Canonical JSON covers packaged prompts and skills, profile name, ordered model and fast-model IDs, deterministic mode, the generated report JSON schema, scorer version and dataset version. Credentials and endpoints are excluded; external model revisions, retrieval settings and mutable knowledge are not captured, so this identifier does not guarantee identical results.

For a behaviour change, update the relevant inputs, bump `SCORER_VERSION` when scoring changes, run `ops-assist profile` with default configuration, and add a dated first entry to `BEHAVIOR_CHANGELOG.md` with that fingerprint, the change, its reason and evaluation result. The offline test checks that the latest entry names the default fingerprint. Use the fingerprint stored with each result to distinguish other profiles and tier comparisons.

## Evaluation release gate

Repeated runs record per-incident rates and a weighted overall pass rate, including errors. The packaged `src/ops_assist/evals/threshold.yaml` contains a justified minimum and its dataset version; `eval run --gate` fails below the minimum or on a version mismatch, and tier comparisons require both tiers to pass. The initial 80% policy is pedagogical and is not a production readiness claim. `eval check-reports DIR` scores each JSON report offline using the same deterministic checks, matching an envelope `incident_id` or the filename stem to the dataset. Invalid or unknown reports fail; an empty directory fails. It checks the supplied files, not dataset coverage, and returns failure if any file fails. Lexical checks are imperfect; no LLM judge is used. See [workshop 33](../ateliers/33-evaluations/README.md).

## Investigation tracing

Tracing is opt-in with `OPS_ASSIST_OTEL=1`. An isolated OpenTelemetry SDK provider exports only ops-assist spans via OTLP/HTTP and the standard `OTEL_EXPORTER_OTLP_ENDPOINT`; the exporter is installed through the optional `otel` extra. The investigation span is the parent of model and tool spans. Model metadata includes agent, requested model and available token counts; tool metadata includes the classified tool name and outcome. Span timestamps supply durations. Arguments, observations, questions, responses and exception messages are not recorded. ADK's built-in legacy telemetry captures content by default; this isolated provider does not install ADK's global exporter. Separately configured global instrumentation remains outside this guarantee. The exporter sends data to the configured endpoint, so use an appropriately trusted collector. The pinned local Jaeger compose configuration and an offline in-memory test path are described in [workshop 34](../ateliers/34-traces/README.md).

## Offline red team probes

`redteam` runs six deterministic probes in temporary state with a scripted ADK model and copied replay data. It checks rollback confirmation, tool and search budgets, bounded logs, and the MCP and A2A read-only surfaces. The audit and simulated writes are checked where applicable; the remote surface probe inspects registration and policy without starting a server. `--fast` skips the poisoned log and `--json` emits structured results. The command does not evaluate a real model or prove resistance to unseen attacks. See [workshop 35](../ateliers/35-red-team/README.md).

## CI/CD gates and image

The workflow runs lint, the complete test suite including the forbidden-terms secret scan, source contract tests, offline report evaluation and fast red-team probes before building an image. The report gate scores only the supplied fixtures and does not measure a live model. On tags, the image is pushed to GHCR and cosign signs its immutable digest using GitHub OIDC; other events build without publishing. The image uses pinned base and uv images, frozen dependencies and a non-root runtime user. Repository branch protection must independently require the gate jobs. See [workshop 36](../ateliers/36-ci-cd/README.md).

## Failure review

The [failure review](failure-review.md) maps the need, available data, validation, costs and ownership to repository evidence. It records the missing owner and the gap between scripted cost scenarios and measured per-investigation monetary cost. [Workshop 37](../ateliers/37-echecs/README.md) applies the same grid offline without adding a CLI command or configuration.

## Platform starter

`new-agent NAME --dir PATH` creates a read-only skeleton in an absent or empty directory. It reuses the platform profile loader, LiteLLM model routing and security callbacks, with writes explicitly disabled. Its fictional example tool is classified as read and returns bounded data; its prompt treats tool results as untrusted. The generated skill is a starting document, not automatically loaded. Offline tests check construction, policy and the evaluation fixture. The generated CI checks out a platform repository and revision configured through repository variables `OPS_ASSIST_REPOSITORY` and `OPS_ASSIST_REF`; select an immutable reviewed revision. The team owns its domain tools, prompt, evaluation and CI configuration. See [workshop 38](../ateliers/38-plateforme/README.md).

## Agent registry

The root `catalog-info.yaml` describes a Backstage Component with an agent extension under `spec.agent`: ownership placeholder, purpose, tool access, rights, configured profile model identifiers, an illustrative monthly budget, and links to evaluation policy and the behaviour changelog. The offline catalog test discovers in-process tools across both topologies with writes enabled, expands the ADK skill toolset, and checks classifications against the security policy, including its default-write rule. The inventory includes ADK's script tool as a write; the bundled skills contain no scripts. External profiles, dynamic tool additions and deployment-specific overrides require separate review. Profile model IDs can be mutable provider aliases; the catalog records identifiers, not guaranteed immutable provider revisions. The budget is informational and is not metered or enforced. No CLI or environment variable is added. See [workshop 39](../ateliers/39-echelle/README.md).
