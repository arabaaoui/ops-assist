"""Command line entry point for the workshops."""

import argparse
import getpass
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import litellm
from litellm.rust_bridge.tokenizer import anthropic
from pydantic import ValidationError

from . import call_metadata
from .config import (
    PROFILES_FILE,
    _load_profiles,
    check_profile_env,
    load_settings,
    missing_fast_keys,
)
from .memory import forget, list_memories
from .observability import ObservationError, ReplaySource
from .report import IncidentReport, check_observation_support
from .run import investigate
from .triage import pretriage


def main(argv: list[str] | None = None) -> int:
    """Parse and execute a command."""
    parser = argparse.ArgumentParser(prog="ops-assist")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new-agent", help="generate a read-only agent skeleton")
    new.add_argument("name")
    new.add_argument("--dir", type=Path, required=True)
    redteam = commands.add_parser("redteam", help="run offline security regression probes")
    redteam.add_argument("--fast", action="store_true")
    redteam.add_argument("--json", action="store_true")
    commands.add_parser("mcp-serve", help="serve read-only observation tools over stdio")
    a2a = commands.add_parser("a2a-serve", help="serve the investigator over A2A on loopback")
    a2a.add_argument("--port", type=int, default=8000)
    eval_parser = commands.add_parser("eval")
    eval_commands = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_commands.add_parser("list")
    eval_cost = eval_commands.add_parser("cost", help="estimate scripted costs offline")
    eval_cost.add_argument("--profile")
    eval_cost.add_argument("--json", action="store_true")
    eval_run = eval_commands.add_parser("run")
    eval_check = eval_commands.add_parser("check-reports")
    eval_check.add_argument("directory")
    eval_run.add_argument("--gate", action="store_true")
    eval_run.add_argument("--profile")
    eval_run.add_argument("--repeat", type=int, default=1)
    eval_run.add_argument("--show-reports", action="store_true")
    eval_run.add_argument("--compare-tiers", action="store_true")
    bench = commands.add_parser("bench", help="measure streamed generation")
    bench.add_argument("--profile")
    bench.add_argument("--runs", type=int, default=3)
    bench.add_argument("--prompt-file", type=Path, required=True)
    bench.add_argument("--allow-remote", action="store_true")
    bench.add_argument("--ollama", action="store_true")
    bench.add_argument("--json", action="store_true")
    doctor = commands.add_parser("doctor", help="inspect local hardware")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--ollama", action="store_true", help="probe local Ollama")
    commands.add_parser("profiles", help="list deployment profiles")
    profile = commands.add_parser("profile")
    profile.add_argument("--list", action="store_true")
    tokens = commands.add_parser("tokens")
    selection = tokens.add_mutually_exclusive_group()
    selection.add_argument("--incident")
    selection.add_argument("--all", action="store_true", help="count every replay incident")
    tokens.add_argument("--model")
    ask = commands.add_parser("ask")
    ask.add_argument("question")
    validate = commands.add_parser("validate")
    validate.add_argument("file", type=Path)
    triage = commands.add_parser("triage")
    triage.add_argument("--incident")
    memory = commands.add_parser("memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_list = memory_commands.add_parser("list")
    memory_list.add_argument("--service")
    memory_forget = memory_commands.add_parser("forget")
    memory_forget.add_argument("--service", required=True)
    feedback = commands.add_parser("feedback")
    feedback.add_argument("action", nargs="?", choices=["export"])
    feedback.add_argument("--report")
    rating = feedback.add_mutually_exclusive_group()
    rating.add_argument("--up", action="store_true")
    rating.add_argument("--down", action="store_true")
    feedback.add_argument("--comment", default="")
    feedback.add_argument("--pairs", action="store_true")
    knowledge = commands.add_parser("knowledge")
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command", required=True)
    knowledge_commands.add_parser("index")
    knowledge_commands.add_parser("eval")
    draft_parser = knowledge_commands.add_parser("draft-postmortem")
    draft_source = draft_parser.add_mutually_exclusive_group()
    draft_source.add_argument("--session")
    draft_source.add_argument("--report", type=Path)
    approve_parser = knowledge_commands.add_parser("approve")
    approve_parser.add_argument("draft_id")
    approve_parser.add_argument("--yes", action="store_true")
    approve_parser.add_argument("--approver")
    approve_parser.add_argument("--accept-edits", action="store_true")
    knowledge_commands.add_parser("stale")
    knowledge_search = knowledge_commands.add_parser("search")
    knowledge_search.add_argument("query")
    knowledge_search.add_argument("-k", type=int, default=5)
    agent = commands.add_parser("investigate")
    agent.add_argument("question")
    agent.add_argument("--incident")
    agent.add_argument("--show-context", action="store_true")
    agent.add_argument("--session")
    args = parser.parse_args(argv)
    try:
        if args.command == "new-agent":
            from .scaffold import new_agent

            new_agent(args.name, args.dir)
            print(f"Created agent {args.name} in {args.dir}")
            return 0
        if args.command == "redteam":
            from .redteam import run_suite

            results = run_suite(fast=args.fast)
            if args.json:
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                print("Probe | Expected | Observed | Result")
                for row in results:
                    status = "PASS" if row["pass"] else "FAIL"
                    print(f"{row['probe']} | {row['expected']} | {row['observed']} | {status}")
            return 0 if results and all(row["pass"] for row in results) else 1
        if args.command == "bench":
            from .bench import benchmark

            env = dict(os.environ)
            if args.profile:
                env["OPS_ASSIST_PROFILE"] = args.profile
            settings = load_settings(env)
            with args.prompt_file.open("rb") as file:
                if os.fstat(file.fileno()).st_size > 65536:
                    raise ValueError("prompt file must be at most 65536 bytes")
                data = file.read(65537)
                if len(data) > 65536:
                    raise ValueError("prompt file must be at most 65536 bytes")
                prompt = data.decode("utf-8")
            result = benchmark(
                settings, prompt, args.runs, allow_remote=args.allow_remote, ollama=args.ollama
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Profile: {result['profile']}  Model: {result['model']}")
                print("Metric                     Median       Min       Max  Samples")
                for name, stats in result["summary"].items():
                    if stats is None:
                        print(f"{name:26} unavailable")
                    else:
                        print(
                            f"{name:26} {stats['median']:9.3f} {stats['min']:9.3f} "
                            f"{stats['max']:9.3f} {stats['samples']:8}"
                        )
                if args.ollama:
                    print(f"Ollama memory: {json.dumps(result['ollama_memory'])}")
            return 0
        if args.command == "doctor":
            from .doctor import diagnose

            result = diagnose(ollama=args.ollama)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"CPU: {result['cpu']['count']} logical CPUs; {result['cpu']['model']}")
                print(
                    f"RAM total bytes: {result['ram']['total_bytes']}; "
                    f"available bytes: {result['ram']['available_bytes']}"
                )
                print(
                    f"GPU: {result['gpu']['name']}; total bytes: {result['gpu']['total_bytes']}; "
                    f"free bytes: {result['gpu']['free_bytes']}"
                )
                print(
                    f"Accelerator: {result['accelerator']['backend']}; "
                    f"driver: {result['accelerator']['version']}"
                )
                if args.ollama:
                    print(f"Ollama: {json.dumps(result['ollama'], ensure_ascii=False)}")
                print(
                    f"Recommended profile: {result['advice']['profile']} — "
                    f"{result['advice']['reason']}"
                )
            return 0
        if args.command == "feedback":
            from .feedback import collect, pairs

            if args.action == "export":
                if not args.pairs or args.report or args.up or args.down or args.comment:
                    raise ValueError("export requires only --pairs")
                for pair in pairs():
                    print(json.dumps(pair, ensure_ascii=False))
            else:
                if not args.report or args.up == args.down or args.pairs:
                    raise ValueError("feedback requires --report and exactly one of --up or --down")
                collect(args.report, "up" if args.up else "down", args.comment)
                print("Feedback saved")
            return 0
        if args.command == "eval":
            from .evaluation_dataset import load_dataset

            if args.eval_command == "cost":
                from .cost import scripted_costs

                env = dict(os.environ)
                if args.profile:
                    env["OPS_ASSIST_PROFILE"] = args.profile
                settings = load_settings(env)
                rows = scripted_costs(settings)
                if args.json:
                    print(json.dumps(rows, indent=2))
                else:
                    print("Scripted estimate in USD; 10 calls per incident, not measured usage")
                    print(
                        "Incident                 cache off / fast off   cache on / fast off   "
                        "cache off / fast on   cache on / fast on"
                    )
                    for row in rows:
                        values = [
                            row[key]
                            for key in (
                                "cache_off_fast_off",
                                "cache_on_fast_off",
                                "cache_off_fast_on",
                                "cache_on_fast_on",
                            )
                        ]
                        formatted = [
                            (f"n/a ({row['reasons'][key]})" if key in row["reasons"] else "unknown")
                            if value is None
                            else ("$0 (local)" if value == 0 else f"${value:.6f}")
                            for key, value in zip(
                                (
                                    "cache_off_fast_off",
                                    "cache_on_fast_off",
                                    "cache_off_fast_on",
                                    "cache_on_fast_on",
                                ),
                                values,
                                strict=True,
                            )
                        ]
                        print(
                            f"{row['incident']:24} "
                            + "  ".join(f"{value:>20}" for value in formatted)
                        )
                    for note in sorted({note for row in rows for note in row["notes"]}):
                        print(f"Note: {note}")
                return 0
            if args.eval_command == "check-reports":
                from .evaluation import check_reports

                result = check_reports(Path(args.directory))
                for row in result["results"]:
                    print(f"{row['file']}: {'PASS' if row['passed'] else 'FAIL'}")
                for incident, rate in result["incident_pass_rates"].items():
                    print(f"{incident}: {rate:.1%}")
                print(f"Pass rate: {result['pass_rate']:.1%}")
                return 0 if all(row["passed"] for row in result["results"]) else 1
            if args.eval_command == "run":
                from .evaluation import (
                    _check_tools_mode,
                    evaluate,
                    evaluate_tiers,
                    gate,
                    load_threshold,
                )

                policy = load_threshold() if args.gate else None

                _check_tools_mode()

                env = dict(os.environ)
                if args.profile:
                    env["OPS_ASSIST_PROFILE"] = args.profile
                settings = load_settings(env)
                check_profile_env(settings, env)
                if args.compare_tiers or os.environ.get("OPS_ASSIST_TOPOLOGY") == "experts":
                    missing = missing_fast_keys(settings, env)
                    if missing:
                        raise ValueError(
                            f"Missing expert environment variable(s): {', '.join(missing)}"
                        )
                if args.compare_tiers:
                    results = evaluate_tiers(settings, args.repeat)
                    print("Sampling variance remains; providers may ignore the fixed seed.")
                    for tier, (result, path) in results.items():
                        print(
                            f"{tier}: pass rate={result['pass_rate']:.1%} "
                            f"total tokens={result['total_tokens']} "
                            f"(approximate calls={result['approximate_calls']}, "
                            f"unknown calls={result['unknown_calls']}) "
                            f"duration={result['duration_seconds']:.2f}s"
                        )
                        for incident, rate in result["incident_pass_rates"].items():
                            print(f"  {incident}: {rate:.1%}")
                        print(f"Result: {path}")
                        if args.show_reports:
                            print(json.dumps(result["results"], ensure_ascii=False, indent=2))
                    return (
                        0
                        if policy is None or all(gate(r, policy) for r, _ in results.values())
                        else 1
                    )
                result, path = evaluate(settings, args.repeat)
                print("Incident                 Run  Valid Status Root Sources Forbidden Result")
                for row in result["results"]:
                    values = " ".join("OK" if value else "FAIL" for value in row["checks"].values())
                    outcome = "PASS" if row["passed"] else "FAIL"
                    print(f"{row['incident']:24} {row['iteration']:3}  {values} {outcome}")
                    if args.show_reports:
                        print(
                            json.dumps(
                                {"report": row["report"], "error": row["error"]},
                                ensure_ascii=False,
                                indent=2,
                            )
                        )
                for incident, rate in result.get("incident_pass_rates", {}).items():
                    print(f"{incident}: {rate:.1%}")
                print(f"Pass rate: {result['pass_rate']:.1%}")
                print(f"Result: {path}")
                if policy is not None:
                    print(
                        f"Gate: {'PASS' if gate(result, policy) else 'FAIL'} "
                        f"(threshold {policy['value']:.1%}, dataset {policy['dataset_version']})"
                    )
                return 0 if policy is None or gate(result, policy) else 1
            dataset = load_dataset()
            print(f"Dataset version: {dataset['version']}")
            for case in dataset["incidents"]:
                print(f"{case['id']}: {case['question']}")
            return 0
        if args.command == "a2a-serve":
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            from .a2a_server import serve

            serve(args.port)
            return 0
        if args.command == "mcp-serve":
            from .mcp_server import serve

            serve()
            return 0
        if args.command == "validate":
            report = IncidentReport.model_validate_json(args.file.read_text(encoding="utf-8"))
            check_observation_support(report)
            print("OK")
            return 0
        if args.command == "profiles" or (args.command == "profile" and args.list):
            path = Path(os.environ.get("OPS_ASSIST_PROFILES_FILE") or PROFILES_FILE)
            for name, profile in _load_profiles(path).items():
                required = ", ".join(profile["requires_env"]) or "none"
                missing = (
                    ", ".join(
                        key
                        for key in profile["requires_env"]
                        if not os.environ.get(key, "").strip()
                    )
                    or "none"
                )
                print(
                    f"{name}: {profile['description']} "
                    f"(location: {profile.get('location', 'unspecified')}; "
                    f"residency: {profile.get('residency', 'unspecified')}; "
                    f"requires: {required}; missing: {missing})"
                )
            return 0
        if args.command == "knowledge":
            from .knowledge.embeddings import configured_embedder
            from .knowledge.index import VectorIndex
            from .security import StateStore

            if args.knowledge_command == "eval":
                from .knowledge.evaluation import evaluate

                for name, (recall, mrr) in evaluate().items():
                    print(f"{name}: recall@5={recall:.3f} MRR@5={mrr:.3f}")
                return 0
            from .knowledge.living import approve, draft, is_stale

            if args.knowledge_command == "draft-postmortem":
                print(draft(args.session, args.report))
                return 0
            if args.knowledge_command == "stale":
                from .knowledge.index import load_documents

                for doc in load_documents():
                    if is_stale(doc["updated"]):
                        print(f"{doc['id']}  {doc['updated']}  {doc['title']}")
                return 0
            if args.knowledge_command == "approve":
                tty = sys.stdin.isatty()
                if args.approver is not None and not args.yes:
                    raise ValueError("--approver requires --yes")
                if not tty and not (
                    args.yes
                    and args.approver
                    and os.environ.get("OPS_ASSIST_ALLOW_NONINTERACTIVE_APPROVAL") == "1"
                ):
                    raise ValueError(
                        "noninteractive approval requires opt-in, --yes and --approver"
                    )
                if args.yes:
                    if not args.approver or not args.approver.strip():
                        raise ValueError("--yes requires a non-empty --approver")
                    approver = args.approver
                else:
                    try:
                        confirmed = input(f"Approve {args.draft_id}? Type yes: ").strip() == "yes"
                        if not confirmed:
                            raise ValueError("approval cancelled")
                        default = getpass.getuser()
                        approver = input(f"Approver [{default}]: ").strip() or default
                    except EOFError as exc:
                        raise ValueError("approval cancelled") from exc
                print(
                    approve(
                        args.draft_id,
                        configured_embedder(),
                        approver,
                        approval="interactive" if tty else "noninteractive",
                        accept_edits=args.accept_edits,
                    )
                )
                return 0
            from .knowledge.retrieval import configured_reranker, search

            embedder = configured_embedder()
            store = StateStore()
            if args.knowledge_command == "index":
                try:
                    previous = VectorIndex.load(store, embedder)
                except FileNotFoundError:
                    previous = None
                except ValueError as exc:
                    if "embedder mismatch" not in str(exc):
                        raise
                    previous = None
                index = VectorIndex.build(embedder, previous)
                index.save(store)
                print(f"Indexed {len(index.chunks)} chunks in {store.root / store.index_name()}")
            else:
                results = search(
                    VectorIndex.load(store, embedder),
                    args.query,
                    args.k,
                    reranker=configured_reranker(),
                )
                if not results:
                    print("retrieval: none")
                for result in results:
                    print(
                        f"{result['score']:.4f}  {result['id']}  {result['title']}  "
                        f"updated={result['updated']} stale={result['stale']} "
                        f"stale_reason={result['stale_reason']}"
                    )
            return 0
        settings = load_settings()
        if args.command in ("ask", "investigate"):
            check_profile_env(settings, dict(os.environ))
        if args.command == "investigate" and os.environ.get("OPS_ASSIST_TOPOLOGY") == "experts":
            missing = missing_fast_keys(settings, dict(os.environ))
            if missing:
                raise ValueError(f"Missing expert environment variable(s): {', '.join(missing)}")
        if args.command == "profile":
            from .fingerprint import fingerprint

            print(settings.describe())
            print(f"Fingerprint: {fingerprint(settings)}")
            for key in settings.requires_env:
                status = "set" if os.environ.get(key, "").strip() else "missing"
                print(f"{key}: {status}")
            if settings.models_overridden:
                print(
                    "OPS_ASSIST_MODELS override: required variables are not checked before calls."
                )
        elif args.command == "tokens":
            from .observability.replay import OBSERVATION_FILES, list_incidents

            incidents = list_incidents() if args.all else [args.incident or settings.incident]
            model = args.model or settings.models[0]
            # Explicitly select LiteLLM's packaged tokenizer: no Hugging Face or tiktoken downloads.
            tokenizer = {"type": "huggingface_tokenizer", "tokenizer": anthropic()}
            print(f"Model: {model}; tokenizer: LiteLLM bundled Anthropic (approximate)")
            info = litellm.model_cost.get(model, {})
            window = info.get("max_input_tokens")
            for incident in incidents:
                source = ReplaySource(incident)
                if args.all:
                    print(f"Incident: {incident}")
                print(f"{'File':24} {'Characters':>12} {'Tokens':>10}")
                total_chars = total_tokens = 0
                for name in sorted(OBSERVATION_FILES):
                    path = source.dir / name
                    if not path.exists() and not path.is_symlink():
                        continue
                    text = source._read(name)
                    count = litellm.token_counter(
                        model=model, text=text, custom_tokenizer=tokenizer
                    )
                    total_chars += len(text)
                    total_tokens += count
                    print(f"{path.name:24} {len(text):12} {count:10}")
                print(f"{'TOTAL':24} {total_chars:12} {total_tokens:10}")
                if isinstance(window, (int, float)) and window > 0:
                    print(
                        f"Context window: {total_tokens / window:.2%} of {window} "
                        "input tokens (approximate)"
                    )
                else:
                    print("Context window: unknown")
        elif args.command == "triage":
            print(
                pretriage(ReplaySource(args.incident or settings.incident)).model_dump_json(
                    indent=2
                )
            )
        elif args.command == "memory":
            if args.memory_command == "forget":
                removed = forget(args.service)
                print(
                    f"Removed {removed} entries"
                    if removed
                    else "Service unknown: 0 entries removed"
                )
            else:
                print(json.dumps(list_memories(args.service), ensure_ascii=False, indent=2))
        elif args.command == "ask":
            kwargs = {"api_base": settings.api_base} if settings.api_base else {}
            response = litellm.completion(
                model=settings.models[0],
                metadata=call_metadata("ask", settings.profile),
                messages=[{"role": "user", "content": args.question}],
                **kwargs,
            )
            print(response.choices[0].message.content)
            print(f"Model: {getattr(response, 'model', None) or 'unknown'}", file=sys.stderr)
        elif args.command == "investigate":
            if args.incident:
                settings = replace(settings, incident=args.incident)
            if args.session and not settings.session_db:
                print(
                    "Warning: session is in memory only and will not survive this process",
                    file=sys.stderr,
                )
            kwargs = {}
            if args.session:
                kwargs["session_id"] = args.session
            if args.show_context:
                kwargs["show_context"] = True
            if os.environ.get("OPS_ASSIST_ALLOW_WRITES") == "1":

                def confirm_tool(name, tool_args):
                    print(
                        f"Confirmation required: {name} {json.dumps(tool_args, ensure_ascii=False)}"
                    )
                    try:
                        return input("Type yes to approve: ").strip() == "yes"
                    except EOFError:
                        return False

                kwargs["confirm_tool"] = confirm_tool
            report, trace = investigate(args.question, settings=settings, **kwargs)
            from .knowledge.living import save_report

            save_report(
                report,
                trace.session_id,
                incident_id=settings.incident
                if os.environ.get("OPS_ASSIST_SOURCE", "replay") == "replay"
                else None,
                question=args.question,
                settings=settings,
            )
            print(report.model_dump_json(indent=2))
            for call in trace:
                suffix = (
                    f" quality={call.retrieval_quality}"
                    if call.retrieval_quality is not None
                    else ""
                )
                print(f"Tool: {call.name} {json.dumps(call.args, ensure_ascii=False)}{suffix}")
            if trace.omitted_calls:
                print(f"... {trace.omitted_calls} more tool calls")
            print(f"Models: {', '.join(trace.models) or 'unknown'}")
            print(f"Session: {trace.session_id}")
            for warning in trace.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
            if args.show_context:
                print(
                    "Turn  Agent  Approximate tokens of the serialized request "
                    "(not the provider's count)"
                )
                for turn, count in enumerate(trace.context_tokens, 1):
                    print(f"{turn:4}  {trace.context_agents[turn - 1]}  {count:>25}")
        return 0
    except (ValueError, OSError, ValidationError, ObservationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
