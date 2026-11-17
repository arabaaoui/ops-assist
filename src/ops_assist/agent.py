"""The ops-assist agent: an incident investigator, read-only at this stage."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.skill_toolset import SkillToolset
from mcp import StdioServerParameters

from .config import Settings, load_settings
from .models import build_model
from .observability import ObservationSource, source_from_env
from .report import IncidentReport
from .tools import make_tools, tool_timeout

logger = logging.getLogger(__name__)

INSTRUCTION = (Path(__file__).resolve().parent / "prompts" / "investigator.md").read_text(
    encoding="utf-8"
)


SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def load_skills():
    """Load the bundled investigation methods and identify invalid files."""
    skills = []
    for name in ("latency", "errors-5xx"):
        directory = SKILLS_DIR / name
        try:
            skill = load_skill_from_dir(directory)
            if not skill.instructions.strip():
                raise ValueError("instructions must not be empty")
            skills.append(skill)
        except (ValueError, OSError) as exc:
            raise ValueError(f"{directory / 'SKILL.md'}: {exc}") from exc
    return skills


def build_agent(settings: Settings | None = None, source: ObservationSource | None = None) -> Agent:
    """Assemble the agent from settings and an observation source (replay by default)."""
    settings = settings or load_settings()
    mode = os.environ.get("OPS_ASSIST_TOOLS", "inprocess")
    if mode not in ("inprocess", "mcp"):
        raise ValueError("OPS_ASSIST_TOOLS must be inprocess or mcp")
    if mode == "mcp" and source is not None:
        raise ValueError("MCP tools require an environment-configured source")
    source = source or source_from_env(settings.incident)
    tools = make_tools(source)
    if mode == "mcp":
        inherited = (
            "OPS_ASSIST_SOURCE",
            "OPS_ASSIST_INCIDENTS_DIR",
            "OPS_ASSIST_PROMETHEUS_URL",
            "OPS_ASSIST_LOKI_URL",
            "OPS_ASSIST_HTTP_TIMEOUT",
            "OPS_ASSIST_TOOL_TIMEOUT",
            "OPS_ASSIST_CHANGES_FILE",
        )
        env = {key: os.environ[key] for key in inherited if key in os.environ}
        env["OPS_ASSIST_INCIDENT"] = settings.incident
        tools = [
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable, args=["-m", "ops_assist.mcp_server"], env=env
                    ),
                    timeout=tool_timeout() + 5.0,
                )
            ),
            next(tool for tool in tools if tool.__name__ == "recall_past_incidents"),
        ]
    tools.append(SkillToolset(skills=load_skills()))
    logger.info("ops-assist: %s source=%s", settings.describe(), source.name)
    return Agent(
        name="ops_assist",
        description="Investigates production incidents from alerts, metrics, logs and changes.",
        model=build_model(settings),
        instruction=INSTRUCTION,
        tools=tools,
        # Tools stay free during the loop; only the final answer must match the schema,
        # and its validators (facts before hypotheses, no action without evidence) run on it.
        output_schema=IncidentReport,
        output_key="report",
    )
