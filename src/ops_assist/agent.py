"""The ops-assist agent: an incident investigator, read-only at this stage."""

from __future__ import annotations

import logging
from pathlib import Path

from google.adk.agents import Agent

from .config import Settings, load_settings
from .models import build_model
from .observability import ObservationSource, source_from_env
from .report import IncidentReport
from .tools import make_tools

logger = logging.getLogger(__name__)

INSTRUCTION = (Path(__file__).resolve().parent / "prompts" / "investigator.md").read_text(
    encoding="utf-8"
)


def build_agent(settings: Settings | None = None, source: ObservationSource | None = None) -> Agent:
    """Assemble the agent from settings and an observation source (replay by default)."""
    settings = settings or load_settings()
    source = source or source_from_env(settings.incident)
    logger.info("ops-assist: %s source=%s", settings.describe(), source.name)
    return Agent(
        name="ops_assist",
        description="Investigates production incidents from alerts, metrics, logs and changes.",
        model=build_model(settings),
        instruction=INSTRUCTION,
        tools=make_tools(source),
        # Tools stay free during the loop; only the final answer must match the schema,
        # and its validators (facts before hypotheses, no action without evidence) run on it.
        output_schema=IncidentReport,
        output_key="report",
    )
