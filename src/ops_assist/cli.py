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

from .config import PROFILES_FILE, _load_profiles, load_settings
from .memory import forget, list_memories
from .observability import ObservationError, ReplaySource
from .report import IncidentReport
from .run import investigate
from .triage import pretriage


def main(argv: list[str] | None = None) -> int:
    """Parse and execute a command."""
    parser = argparse.ArgumentParser(prog="ops-assist")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp-serve", help="serve read-only observation tools over stdio")
    a2a = commands.add_parser("a2a-serve", help="serve the investigator over A2A on loopback")
    a2a.add_argument("--port", type=int, default=8000)
    profile = commands.add_parser("profile")
    profile.add_argument("--list", action="store_true")
    tokens = commands.add_parser("tokens")
    tokens.add_argument("--incident")
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
            IncidentReport.model_validate_json(args.file.read_text(encoding="utf-8"))
            print("OK")
            return 0
        if args.command == "profile" and args.list:
            path = Path(os.environ.get("OPS_ASSIST_PROFILES_FILE") or PROFILES_FILE)
            for name, profile in _load_profiles(path).items():
                required = ", ".join(profile["requires_env"]) or "none"
                print(f"{name}: {profile['description']} (requires: {required})")
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
        if args.command in ("ask", "investigate") and not settings.models_overridden:
            missing = [key for key in settings.requires_env if not os.environ.get(key, "").strip()]
            if missing:
                raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")
        if args.command == "profile":
            print(settings.describe())
            for key in settings.requires_env:
                status = "set" if os.environ.get(key, "").strip() else "missing"
                print(f"{key}: {status}")
            if settings.models_overridden:
                print(
                    "OPS_ASSIST_MODELS override: required variables are not checked before calls."
                )
        elif args.command == "tokens":
            source = ReplaySource(args.incident or settings.incident)
            model = args.model or settings.models[0]
            # Explicitly select LiteLLM's packaged tokenizer: no Hugging Face or tiktoken downloads.
            tokenizer = {"type": "huggingface_tokenizer", "tokenizer": anthropic()}
            print(f"Model: {model}; tokenizer: LiteLLM bundled Anthropic (approximate)")
            print(f"{'File':24} {'Characters':>12} {'Tokens':>10}")
            total_chars = total_tokens = 0
            for path in sorted(source.dir.iterdir()):
                if not path.is_file() or path.name == "expected.json":
                    continue
                text = path.read_text(encoding="utf-8")
                count = litellm.token_counter(model=model, text=text, custom_tokenizer=tokenizer)
                total_chars += len(text)
                total_tokens += count
                print(f"{path.name:24} {len(text):12} {count:10}")
            print(f"{'TOTAL':24} {total_chars:12} {total_tokens:10}")
            info = litellm.model_cost.get(model, {})
            window = info.get("max_input_tokens")
            if window:
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

            save_report(report, trace.session_id)
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
