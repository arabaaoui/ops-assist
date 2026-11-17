"""Run one investigation and collect its tool calls."""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import litellm
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from litellm.rust_bridge.tokenizer import anthropic

from .agent import build_agent
from .config import Settings, load_settings
from .memory import SECRET, remember
from .observability import ObservationSource, source_from_env
from .report import CHUNK_ID, IncidentReport, check_observation_support, knowledge_citations
from .security import _redact
from .triage import pretriage

logger = logging.getLogger(__name__)
MAX_TRACE_CALLS = 50
MAX_TRACE_VALUE = 200


@dataclass
class ToolCallTrace:
    """A tool invocation emitted by the model."""

    name: str
    args: dict[str, Any]
    retrieval_quality: str | None = None


class InvestigationTrace(list[ToolCallTrace]):
    """Tool calls with an approximate prompt size for each model turn."""

    def __init__(self) -> None:
        """Start an empty trace."""
        super().__init__()
        self.context_tokens: list[int] = []
        self.context_agents: list[str] = []
        self.session_id = ""
        self.warnings: list[str] = []
        self.models: list[str] = []
        self.omitted_calls = 0
        self._pending: dict[str, ToolCallTrace] = {}

    def record_call(self, call) -> None:
        """Retain a bounded, redacted view of a call, keyed by its ADK ID."""
        if len(self) >= MAX_TRACE_CALLS:
            self.omitted_calls += 1
            return
        clean = _redact(dict(call.args or {}))
        args = {}
        for key, value in list(clean.items())[:50]:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, str):
                value = value[:MAX_TRACE_VALUE]
            if not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)
            if not isinstance(value, str) and len(str(value)) > MAX_TRACE_VALUE:
                value = str(value)[:MAX_TRACE_VALUE]
            args[SECRET.sub("[redacted]", key)[:MAX_TRACE_VALUE]] = value
        item = ToolCallTrace(
            str(call.name or "")[:MAX_TRACE_VALUE],
            args,
            "outcome unknown" if call.name == "search_knowledge" else None,
        )
        self.append(item)
        if call.id:
            self._pending[call.id] = item

    def record_response(self, response) -> None:
        """Associate a response only when ADK provides a matching call ID."""
        item = self._pending.pop(response.id, None) if response.id else None
        if item and item.name == "search_knowledge":
            result = response.response or {}
            quality = result.get("retrieval_quality")
            reason = result.get("reason")
            status = result.get("status")
            item.retrieval_quality = (
                quality
                if quality in ("good", "weak", "none")
                else reason
                if reason
                in (
                    "knowledge_search_limit",
                    "tool_call_limit",
                    "delegation_limit",
                    "read_only",
                    "audit_unavailable",
                )
                else status
                if status in ("error", "denied")
                else "outcome unknown"
            )


def investigate(
    question: str,
    settings: Settings | None = None,
    source: ObservationSource | None = None,
    model: BaseLlm | None = None,
    session_id: str | None = None,
    show_context: bool = False,
    confirm_tool: Callable[[str, dict[str, Any]], bool] | None = None,
) -> tuple[IncidentReport, InvestigationTrace]:
    """Run an investigation in a new or resumed session and validate its report."""
    settings = settings or load_settings()
    explicit_source = source is not None
    source = source or source_from_env(settings.incident)
    try:
        triage = pretriage(source)
        data = triage.model_dump_json()
        services = triage.affected_services
    except Exception as exc:  # noqa: BLE001 - pre-triage must not block investigation
        logger.warning("Pre-triage unavailable: %s", exc)
        data = json.dumps({"status": "unavailable", "reason": str(exc)[:200]})
        services = []
    if os.environ.get("OPS_ASSIST_TOOLS", "inprocess") == "mcp":
        if explicit_source:
            raise ValueError("MCP tools require an environment-configured source")
        agent = build_agent(settings)
    else:
        agent = build_agent(settings, source)
    trace = InvestigationTrace()

    def measure(callback_context, llm_request):
        try:
            payload = llm_request.model_dump_json(exclude_none=True)
            tokenizer = {"type": "huggingface_tokenizer", "tokenizer": anthropic()}
            count = litellm.token_counter(model="", text=payload, custom_tokenizer=tokenizer)
            trace.context_tokens.append(count)
            trace.context_agents.append(callback_context.agent_name)
        except Exception:  # noqa: BLE001 - measurement must not stop an investigation
            logger.exception("Context measurement failed")
        return None

    if show_context:
        for candidate in [agent, *agent.sub_agents]:
            candidate.before_model_callback = measure
    if model is not None:
        agent.model = model
        for expert in agent.sub_agents:
            expert.model = model
    if settings.session_db:
        runner = Runner(
            agent=agent,
            app_name="ops_assist",
            session_service=SqliteSessionService(settings.session_db),
        )
    else:
        runner = InMemoryRunner(agent=agent, app_name="ops_assist")

    async def run() -> tuple[IncidentReport, InvestigationTrace]:
        session = None
        if session_id:
            session = await runner.session_service.get_session(
                app_name="ops_assist", user_id="user", session_id=session_id
            )
        if session is None:
            session = await runner.session_service.create_session(
                app_name="ops_assist", user_id="user", session_id=session_id
            )
        trace.session_id = session.id
        safe_data = data.replace("<", "\\u003c").replace(">", "\\u003e")
        message = types.Content(
            role="user",
            parts=[
                types.Part(text=f"{question}\n\n<pretriage_data>\n{safe_data}\n</pretriage_data>")
            ],
        )
        current_report = None
        while True:
            confirmations = []
            async for event in runner.run_async(
                user_id="user", session_id=session.id, new_message=message
            ):
                if event.model_version and event.model_version not in trace.models:
                    trace.models.append(event.model_version)
                if event.actions and "report" in event.actions.state_delta:
                    current_report = event.actions.state_delta["report"]
                for part in event.content.parts if event.content and event.content.parts else []:
                    if part.function_call:
                        call = part.function_call
                        if call.name == "adk_request_confirmation":
                            confirmations.append(call)
                        else:
                            trace.record_call(call)
                    if part.function_response:
                        trace.record_response(part.function_response)
            if not confirmations:
                break
            if confirm_tool is None:
                raise ValueError("Tool confirmation required; use an interactive client")
            parts = []
            for call in confirmations:
                original = call.args["originalFunctionCall"]
                approved = confirm_tool(original["name"], original.get("args", {}))
                parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response={"confirmed": approved}
                        )
                    )
                )
            message = types.Content(role="user", parts=parts)
        if current_report is None:
            raise ValueError("agent returned no report")
        report = IncidentReport.model_validate(current_report)
        check_observation_support(report)
        citations = knowledge_citations(report)
        report.citation_warnings = [
            f"Fact {i}: knowledge, not observation ({fact.source})"
            for i, fact in enumerate(report.facts)
            if CHUNK_ID.search(fact.source)
        ]
        if citations:
            from .knowledge.embeddings import configured_embedder
            from .knowledge.index import VectorIndex
            from .security import StateStore

            try:
                index = VectorIndex.load(StateStore(), configured_embedder())
                known = {chunk["id"] for chunk in index.chunks}
                report.citation_warnings.extend(
                    f"Unknown knowledge citation: {s}" for s in sorted(citations - known)
                )
            except (OSError, ValueError, TypeError):
                report.citation_warnings.append(
                    "Knowledge citations could not be verified: index unavailable"
                )
            trace.warnings.extend(report.citation_warnings)
        try:
            remember(report, services)
        except Exception:  # noqa: BLE001 - preserve a valid report
            logger.exception("Could not save investigation memory")
            trace.warnings.append("Could not save investigation memory")
        return report, trace

    async def run_and_close():
        try:
            if os.environ.get("OPS_ASSIST_TOOLS", "inprocess") == "mcp":
                try:
                    toolsets = [tool for tool in agent.tools if isinstance(tool, McpToolset)]
                    toolsets += [
                        nested
                        for expert in agent.sub_agents
                        for nested in expert.tools
                        if isinstance(nested, McpToolset)
                    ]
                    for toolset in toolsets:
                        await toolset.get_tools()
                except Exception as exc:
                    raise ValueError(
                        "Could not start ops-assist MCP server; try OPS_ASSIST_TOOLS=inprocess"
                    ) from exc
            return await run()
        finally:
            await runner.close()

    return asyncio.run(run_and_close())
