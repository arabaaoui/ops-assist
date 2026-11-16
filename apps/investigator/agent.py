"""Entry point for the ADK developer UI: `uv run adk web apps`."""

from ops_assist.agent import build_agent

root_agent = build_agent()
