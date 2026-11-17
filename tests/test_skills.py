"""Bundled skills are validated at startup and available in the ADK loop."""

import json
import re
from pathlib import Path

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types
from test_agent_loop import _run

from ops_assist.agent import build_agent, load_skills
from ops_assist.config import load_settings


def test_bundled_skills_are_valid_and_include_investigation_methods():
    skills = {skill.name: skill for skill in load_skills()}
    assert set(skills) == {"latency", "errors-5xx"}
    for skill in skills.values():
        assert skill.description and "logs" in skill.instructions.lower()
        assert "hypotheses" in skill.instructions.lower()


@pytest.mark.parametrize(
    ("name", "triggers"),
    [
        ("latency", ["slow", "slowness", "latency", "p95/p99", "timeouts", "response time"]),
        ("errors-5xx", ["5xx", "500/502/503/504", "error rate", "failing requests"]),
    ],
)
def test_skill_describes_triggers_and_grounded_method(name, triggers):
    skill = next(skill for skill in load_skills() if skill.name == name)
    assert all(trigger in skill.description.lower() for trigger in triggers)
    tools = ("get_alerts", "get_metric", "get_logs", "get_changes", "recall_past_incidents")
    assert all(f"`{tool}`" in skill.instructions for tool in tools)
    expected_metrics = {
        "http_request_duration_p95_seconds",
        "http_error_ratio",
        "cpu_usage_ratio",
        "db_pool_connections_in_use",
    }
    metrics_path = (
        Path(__file__).resolve().parents[1]
        / "src/ops_assist/data/incidents"
        / "payment-latency/metrics.json"
    )
    actual_metrics = {entry["name"] for entry in json.loads(metrics_path.read_text())}
    cited_metrics = set(re.findall(r"`((?:http|cpu|db)_[a-z0-9_]+)`", skill.instructions))
    assert cited_metrics == expected_metrics
    assert cited_metrics <= actual_metrics
    assert "root_cause_identified" in skill.instructions
    assert "hypotheses_only" in skill.instructions
    assert "same service AND" in skill.instructions
    assert "log or metric" in skill.instructions


@pytest.mark.parametrize(
    "content",
    [
        "not frontmatter",
        "---\nname: bad\n---\nbody",
        "---\nname: latency\ndescription: test\n---\n",
    ],
)
def test_invalid_skill_fails_agent_startup_with_filename(tmp_path, monkeypatch, content):
    import ops_assist.agent as agent_module

    directory = tmp_path / "latency"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(agent_module, "SKILLS_DIR", tmp_path)
    with pytest.raises(ValueError, match="SKILL.md") as error:
        build_agent(load_settings(env={}))
    assert str(path) in str(error.value)


class SkillModel(BaseLlm):
    model: str = "scripted-skills"
    seen: list = []
    skill_name: str = "latency"

    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in (c.parts or [])
            if p.function_response
        ]
        if not responses:
            part = types.Part(function_call=types.FunctionCall(name="list_skills", args={}))
        elif len(responses) == 1:
            self.seen.append(responses[-1].response)
            part = types.Part(
                function_call=types.FunctionCall(
                    name="load_skill", args={"skill_name": self.skill_name}
                )
            )
        else:
            self.seen.append(responses[-1].response)
            report = {
                "summary": "No evidence collected.",
                "status": "hypotheses_only",
                "facts": [],
                "hypotheses": [],
                "unknowns": ["observations"],
            }
            part = types.Part(text=json.dumps(report))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.parametrize(
    ("skill_name", "expected"), [("latency", "percentiles"), ("errors-5xx", "error rate")]
)
def test_agent_exposes_and_loads_skills_in_adk_loop(skill_name, expected):
    agent = build_agent(load_settings(env={}))
    assert any(isinstance(tool, SkillToolset) for tool in agent.tools)
    model = SkillModel(seen=[], skill_name=skill_name)
    agent.model = model
    _run(agent, "Investigate latency")
    assert "latency" in str(model.seen[0]) and "errors-5xx" in str(model.seen[0])
    assert model.seen[1]["skill_name"] == skill_name
    assert expected in model.seen[1]["instructions"]


def test_mcp_agent_also_registers_skills(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    agent = build_agent(load_settings(env={}))
    assert any(isinstance(tool, SkillToolset) for tool in agent.tools)
