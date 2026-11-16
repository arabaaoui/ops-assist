"""Offline MCP transport and ADK integration."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import ops_assist.agent as agent_module
from ops_assist import mcp_server
from ops_assist.agent import build_agent
from ops_assist.config import load_settings
from ops_assist.observability import ReplaySource
from ops_assist.run import investigate
from ops_assist.tools import MCP_EXPOSED_TOOLS, make_tools


@pytest.fixture(autouse=True)
def subprocess_sandbox_tick(monkeypatch, tmp_path):
    """Inject the sandbox wakeup workaround only into test subprocesses."""
    if os.environ.get("OPS_ASSIST_TEST_ASYNC_TICK") != "1":
        return
    (tmp_path / "sitecustomize.py").write_text(
        "import asyncio\n"
        "original = asyncio.DefaultEventLoopPolicy.new_event_loop\n"
        "def new_loop(self):\n"
        "    loop = original(self)\n"
        "    def tick():\n"
        "        loop.call_soon(tick)\n"
        "    loop.call_soon(tick)\n"
        "    return loop\n"
        "asyncio.DefaultEventLoopPolicy.new_event_loop = new_loop\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    original = agent_module.StdioServerParameters

    def params_with_tick(**kwargs):
        kwargs["env"]["PYTHONPATH"] = str(tmp_path)
        return original(**kwargs)

    monkeypatch.setattr(agent_module, "StdioServerParameters", params_with_tick)


class EnvelopeModel(BaseLlm):
    model: str = "scripted"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response.response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if not responses:
            part = types.Part(function_call=types.FunctionCall(name="get_alerts", args={}))
        else:
            self.seen.append(responses[-1])
            data = responses[-1]["structuredContent"]
            alerts = data.get("alerts", [])
            report = {
                "summary": f"{len(alerts)} alerts.",
                "status": "hypotheses_only",
                "facts": [{"statement": a["summary"], "source": a["source"]} for a in alerts],
                "hypotheses": [],
                "unknowns": ["additional evidence"],
            }
            part = types.Part(text=json.dumps(report))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_registration_is_allowlisted_and_refuses_missing(monkeypatch):
    assert MCP_EXPOSED_TOOLS == ("get_alerts", "get_metric", "get_logs", "get_changes")
    registered = []

    class Server:
        def __init__(self, name):
            pass

        def add_tool(self, tool):
            registered.append(tool.__name__)

        def run(self, transport):
            assert transport == "stdio"

    async def write_tool():
        pass

    source = ReplaySource("payment-latency")
    tools = make_tools(source)
    monkeypatch.setattr(mcp_server, "source_from_env", lambda incident: source)
    monkeypatch.setattr(mcp_server, "MCPServer", Server)
    monkeypatch.setattr(mcp_server, "make_tools", lambda source: [write_tool, *reversed(tools)])
    mcp_server.serve()
    assert tuple(registered) == MCP_EXPOSED_TOOLS
    monkeypatch.setattr(mcp_server, "make_tools", lambda source: [write_tool])
    with pytest.raises(ValueError, match="missing tools.*get_alerts"):
        mcp_server.serve()


def test_stdio_server_parity_and_discovery(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "replay")
    monkeypatch.setenv("OPS_ASSIST_INCIDENT", "payment-latency")

    async def check():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "ops_assist.cli", "mcp-serve"], env=dict(os.environ)
        )
        async with (
            stdio_client(params) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            await asyncio.wait_for(session.initialize(), 20)
            discovered = await session.list_tools()
            assert {tool.name for tool in discovered.tools} == set(MCP_EXPOSED_TOOLS)
            direct = {tool.__name__: tool for tool in make_tools(ReplaySource("payment-latency"))}
            cases = [
                ("get_alerts", {}),
                (
                    "get_metric",
                    {"name": "http_request_duration_p95_seconds", "service": "payment-api"},
                ),
                ("get_logs", {"service": "payment-api", "limit": 1}),
                ("get_changes", {"service": "payment-api"}),
                ("get_metric", {"name": "unknown", "service": "unknown"}),
                ("get_logs", {"service": "unknown"}),
                ("get_changes", {"service": "unknown"}),
            ]
            for name, args in cases:
                result = await session.call_tool(name, args)
                expected = await direct[name](**args)
                assert not result.is_error
                assert result.structured_content == expected
                assert expected["status"] == ("error" if args.get("service") == "unknown" else "ok")

    asyncio.run(check())


def test_agent_receives_the_mcp_envelope(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "replay")
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path))
    model = EnvelopeModel(seen=[])
    report, trace = investigate("Why?", model=model)
    assert report.summary == "2 alerts."
    assert trace[0].name == "get_alerts"
    result = model.seen[0]
    assert result["structuredContent"] == asyncio.run(
        make_tools(ReplaySource("payment-latency"))[0]()
    )
    assert result["content"] and result["isError"] is False


def test_selection_and_environment(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "invalid")
    with pytest.raises(ValueError, match="OPS_ASSIST_TOOLS"):
        build_agent(load_settings(env={}))
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    with pytest.raises(ValueError, match="environment-configured"):
        investigate("Why?", source=ReplaySource("payment-latency"))
    monkeypatch.setattr(agent_module, "StdioServerParameters", StdioServerParameters)
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "replay")
    monkeypatch.setenv("OPS_ASSIST_TOOL_TIMEOUT", "0.2")
    monkeypatch.setenv("OPENAI_API_KEY", "private")
    settings = replace(load_settings(env={}), incident="payment-latency")
    original = agent_module.make_tools
    monkeypatch.setattr(agent_module, "make_tools", lambda source: list(reversed(original(source))))
    agent = build_agent(settings)
    connection = agent.tools[0].connection_params
    assert connection.timeout == 5.2
    assert connection.server_params.env["OPS_ASSIST_INCIDENT"] == settings.incident
    assert connection.server_params.env["OPS_ASSIST_SOURCE"] == "replay"
    assert "PYTHONPATH" not in connection.server_params.env
    assert "OPENAI_API_KEY" not in connection.server_params.env
    assert agent.tools[1].__name__ == "recall_past_incidents"
    with pytest.raises(ValueError, match="environment-configured"):
        build_agent(settings, ReplaySource("payment-latency"))


def test_server_stdout_contains_only_json_rpc(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "replay")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    result = subprocess.run(
        [sys.executable, "-m", "ops_assist.cli", "mcp-serve"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert "Starting ops-assist MCP server" in result.stderr
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(messages) == 1 and messages[0]["jsonrpc"] == "2.0"
    assert messages[0]["id"] == 1 and "result" in messages[0]


def test_startup_failure_is_explained(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    original = agent_module.StdioServerParameters

    def broken(**kwargs):
        kwargs["args"] = ["-c", "raise SystemExit(1)"]
        return original(**kwargs)

    monkeypatch.setattr(agent_module, "StdioServerParameters", broken)
    with pytest.raises(ValueError, match="MCP server.*OPS_ASSIST_TOOLS=inprocess"):
        investigate("Why?", model=EnvelopeModel(seen=[]))


def test_server_tool_timeout_reaches_adk_client(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "replay")
    monkeypatch.setenv("OPS_ASSIST_TOOL_TIMEOUT", "0.15")
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path / "memory"))
    script = tmp_path / "slow_server.py"
    script.write_text(
        "import time\n"
        "from ops_assist import mcp_server\n"
        "from ops_assist.observability import ReplaySource\n"
        "class Slow(ReplaySource):\n"
        "    def alerts(self):\n"
        "        time.sleep(1)\n"
        "        return super().alerts()\n"
        "mcp_server.source_from_env = lambda incident: Slow(incident)\n"
        "mcp_server.serve()\n"
    )
    original = agent_module.StdioServerParameters

    def slow_server(**kwargs):
        kwargs["args"] = [str(script)]
        return original(**kwargs)

    monkeypatch.setattr(agent_module, "StdioServerParameters", slow_server)
    model = EnvelopeModel(seen=[])
    investigate("Why?", model=model)
    assert model.seen[0]["structuredContent"] == {
        "status": "error",
        "error": "get_alerts timed out after 0.15 seconds",
    }
