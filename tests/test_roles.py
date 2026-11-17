"""Offline tests for the coordinator and its bounded experts."""

import asyncio
import json

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from ops_assist.agent import build_agent
from ops_assist.config import load_settings
from ops_assist.run import investigate


class RolesModel(BaseLlm):
    model: str = "scripted"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        names = {
            d.name for t in llm_request.config.tools or [] for d in t.function_declarations or []
        }
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if "get_alerts" in names:
            responses = [r for r in responses if r.name == "get_alerts"]
            if not responses:
                part = types.Part(function_call=types.FunctionCall(name="get_alerts", args={}))
            else:
                data = responses[-1].response
                data = data.get("structuredContent", data)
                self.seen.append(data)
                part = types.Part(text="Alerts: " + json.dumps(data))
        elif "get_changes" in names:
            responses = [r for r in responses if r.name == "get_changes"]
            if not responses:
                part = types.Part(
                    function_call=types.FunctionCall(
                        name="get_changes", args={"service": "payment-api"}
                    )
                )
            else:
                data = responses[-1].response
                data = data.get("structuredContent", data)
                self.seen.append(data)
                part = types.Part(text="Changes: " + json.dumps(data))
        elif not [r for r in responses if r.name in {"metrics_expert", "logs_expert"}]:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="metrics_expert", args={"request": "Find alerts"}
                )
            )
        elif not any(r.name == "logs_expert" for r in responses):
            assert "Alerts:" in str(responses[-1].response)
            part = types.Part(
                function_call=types.FunctionCall(
                    name="logs_expert", args={"request": "Find changes"}
                )
            )
        else:
            assert "Changes:" in str(responses[-1].response)
            part = types.Part(
                text=json.dumps(
                    {
                        "summary": "Investigation complete",
                        "status": "hypotheses_only",
                        "facts": [],
                        "hypotheses": [],
                        "unknowns": ["cause"],
                    }
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_topology_ownership_and_validation(monkeypatch):
    settings = load_settings(env={})
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "bad")
    with pytest.raises(ValueError, match="OPS_ASSIST_TOPOLOGY"):
        build_agent(settings)
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    agent = build_agent(settings)
    experts = {e.name: e for e in agent.sub_agents}
    assert set(experts) == {"metrics_expert", "logs_expert"}
    sets = [{t.__name__ for t in e.tools} for e in experts.values()]
    assert sets == [{"get_alerts", "get_metric"}, {"get_logs", "get_changes"}]
    assert sets[0].isdisjoint(sets[1])
    assert all(
        not e.sub_agents
        and e.mode == "single_turn"
        and e.disallow_transfer_to_peers
        and e.disallow_transfer_to_parent
        for e in experts.values()
    )
    assert [t.__name__ for t in agent.tools if callable(t)] == [
        "recall_past_incidents",
        "search_knowledge",
        "get_dependencies",
    ]
    assert "Delegate metrics" in agent.instruction
    assert all("pretriage_data" in expert.instruction for expert in experts.values())


@pytest.mark.parametrize("mode", ["inprocess", "mcp"])
def test_experts_execute_and_return_to_coordinator(monkeypatch, mode, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    monkeypatch.setenv("OPS_ASSIST_TOOLS", mode)
    if mode == "mcp":
        # Reuse the subprocess event-loop workaround used by the MCP suite.
        from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
        from mcp import StdioServerParameters

        import ops_assist.agent as module

        del StdioConnectionParams
        (tmp_path / "sitecustomize.py").write_text(
            "import asyncio\noriginal = asyncio.DefaultEventLoopPolicy.new_event_loop\n"
            "def new_loop(self):\n loop = original(self)\n def tick(): loop.call_soon(tick)\n"
            " loop.call_soon(tick)\n return loop\n"
            "asyncio.DefaultEventLoopPolicy.new_event_loop = new_loop\n"
        )

        def params(**kwargs):
            kwargs["env"]["PYTHONPATH"] = str(tmp_path)
            return StdioServerParameters(**kwargs)

        monkeypatch.setattr(module, "StdioServerParameters", params)
        agent = build_agent(load_settings(env={}))
        experts = agent.sub_agents

        async def discover():
            try:
                return [{t.name for t in await e.tools[0].get_tools()} for e in experts]
            finally:
                for e in experts:
                    await e.tools[0].close()

        assert asyncio.run(discover()) == [
            {"get_alerts", "get_metric"},
            {"get_logs", "get_changes"},
        ]
    model = RolesModel(seen=[])
    report, trace = investigate("Why?", model=model, show_context=True)
    assert set(trace.context_agents) == {"ops_assist", "metrics_expert", "logs_expert"}
    assert len(trace.context_agents) == len(trace.context_tokens)
    assert report.summary == "Investigation complete"
    assert [t.name for t in trace] == ["metrics_expert", "get_alerts", "logs_expert", "get_changes"]
    assert len(model.seen) == 2 and all(x["status"] == "ok" for x in model.seen)


@pytest.mark.parametrize(
    "profile", ["local", "gemini", "api", "openai", "anthropic", "mistral", "openrouter", "mixed"]
)
def test_experts_use_every_configured_profile(monkeypatch, profile):
    import ops_assist.agent as module

    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    settings = load_settings(env={"OPS_ASSIST_PROFILE": profile})
    calls = []

    def model_for(resolved, agent_name="ops_assist"):
        calls.append(resolved)
        return RolesModel(seen=[])

    monkeypatch.setattr(module, "build_model", model_for)
    agent = build_agent(settings)
    assert calls == [settings, settings, settings]
    assert len(agent.sub_agents) == 2


class ForbiddenCallModel(BaseLlm):
    model: str = "scripted"
    forbidden: str

    async def generate_content_async(self, llm_request, stream=False):
        names = {
            d.name for t in llm_request.config.tools or [] for d in t.function_declarations or []
        }
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if "get_alerts" in names and any(r.name == self.forbidden for r in responses):
            part = types.Part(text="The attempted tool was refused.")
        elif "get_alerts" in names:
            args = (
                {"service": "payment-api"}
                if self.forbidden == "get_logs"
                else {"agent_name": "logs_expert"}
            )
            part = types.Part(function_call=types.FunctionCall(name=self.forbidden, args=args))
        elif not any(r.name == "metrics_expert" for r in responses):
            part = types.Part(
                function_call=types.FunctionCall(name="metrics_expert", args={"request": "Check"})
            )
        else:
            part = types.Part(
                text=json.dumps(
                    {
                        "summary": "Expert unavailable",
                        "status": "hypotheses_only",
                        "facts": [],
                        "hypotheses": [],
                        "unknowns": ["evidence"],
                    }
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.parametrize("forbidden", ["get_logs", "transfer_to_agent"])
def test_expert_forbidden_calls_are_refused_in_events(monkeypatch, forbidden):
    from google.adk.runners import InMemoryRunner

    from ops_assist.observability import ReplaySource

    class WatchedSource(ReplaySource):
        log_calls = 0

        def logs(self, *args, **kwargs):
            self.log_calls += 1
            return super().logs(*args, **kwargs)

    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    source = WatchedSource("payment-latency")
    agent = build_agent(load_settings(env={}), source)
    model = ForbiddenCallModel(forbidden=forbidden)
    agent.model = model
    for expert in agent.sub_agents:
        expert.model = model

    async def run():
        runner = InMemoryRunner(agent=agent, app_name="ops_assist")
        events = []
        try:
            session = await runner.session_service.create_session(
                app_name="ops_assist", user_id="u"
            )
            message = types.Content(role="user", parts=[types.Part(text="Investigate")])
            async for event in runner.run_async(
                user_id="u", session_id=session.id, new_message=message
            ):
                events.append(event)
            return events
        finally:
            await runner.close()

    events = asyncio.run(run())
    assert source.log_calls == 0
    assert any(
        e.author == "metrics_expert"
        and any(
            p.function_call and p.function_call.name == forbidden for p in e.content.parts or []
        )
        for e in events
        if e.content
    )
    assert any(
        e.author == "metrics_expert"
        and any(
            p.function_response
            and p.function_response.name == forbidden
            and "no tool with that name" in p.function_response.response.get("error", "")
            for p in e.content.parts or []
        )
        for e in events
        if e.content
    )
    assert all(not e.actions.transfer_to_agent for e in events)
    assert not any(e.author == "logs_expert" for e in events)
    assert any(e.actions.state_delta.get("report") for e in events)
