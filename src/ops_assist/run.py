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
from .memory import remember
from .observability import ObservationSource, source_from_env
from .report import IncidentReport
from .triage import pretriage

logger = logging.getLogger(__name__)


@dataclass
class ToolCallTrace:
    """A tool invocation emitted by the model."""

    name: str
    args: dict[str, Any]


class InvestigationTrace(list[ToolCallTrace]):
    """Tool calls with an approximate prompt size for each model turn."""

    def __init__(self) -> None:
        """Start an empty trace."""
        super().__init__()
        self.context_tokens: list[int] = []
        self.session_id = ""
        self.warnings: list[str] = []


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
        del callback_context
        try:
            payload = llm_request.model_dump_json(exclude_none=True)
            tokenizer = {"type": "huggingface_tokenizer", "tokenizer": anthropic()}
            trace.context_tokens.append(
                litellm.token_counter(model="", text=payload, custom_tokenizer=tokenizer)
            )
        except Exception:  # noqa: BLE001 - measurement must not stop an investigation
            logger.exception("Context measurement failed")
        return None

    if show_context:
        agent.before_model_callback = measure
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
                if event.actions and "report" in event.actions.state_delta:
                    current_report = event.actions.state_delta["report"]
                for part in event.content.parts if event.content and event.content.parts else []:
                    if part.function_call:
                        call = part.function_call
                        if call.name == "adk_request_confirmation":
                            confirmations.append(call)
                        else:
                            trace.append(ToolCallTrace(call.name, dict(call.args or {})))
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
