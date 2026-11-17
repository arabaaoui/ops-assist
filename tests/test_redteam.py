"""The probes must detect disabled guards, without a model or network."""

import json
import socket

import pytest
from google.adk.tools import FunctionTool

from ops_assist import cli, redteam, tools
from ops_assist.security import SecurityBoundary


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("network access forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.mark.parametrize("probe", redteam.PROBES, ids=lambda probe: probe.id)
def test_probe_passes(probe):
    passed, observed = probe.run()
    assert passed, observed


def test_confirmation_mutation_is_detected(monkeypatch):
    async def no_confirmation(*args, **kwargs):
        return False

    monkeypatch.setattr(FunctionTool, "check_require_confirmation", no_confirmation)
    for probe in (redteam.poisoned_log, redteam.rollback_without_confirmation):
        assert not probe()[0]


@pytest.mark.parametrize(
    ("probe", "attribute"),
    [(redteam.tool_budget, "max_calls"), (redteam.search_loop, "max_searches")],
)
def test_budget_mutation_is_detected(monkeypatch, probe, attribute):
    original = SecurityBoundary.__init__

    def unlimited(self, *args, **kwargs):
        original(self, *args, **kwargs)
        setattr(self, attribute, 1000)

    monkeypatch.setattr(SecurityBoundary, "__init__", unlimited)
    assert not probe()[0]


def test_output_bound_mutation_is_detected(monkeypatch):
    monkeypatch.setattr(tools, "_bounded", lambda value: (value, False))
    assert not redteam.oversized_output()[0]


def test_remote_surface_mutation_is_detected(monkeypatch):
    from ops_assist import mcp_server

    monkeypatch.setattr(
        mcp_server, "MCP_EXPOSED_TOOLS", (*mcp_server.MCP_EXPOSED_TOOLS, "rollback_deployment")
    )
    assert not redteam.remote_write_surface()[0]


def test_a2a_protection_mutation_is_detected(monkeypatch):
    from ops_assist import a2a_server

    monkeypatch.setattr(a2a_server, "create_app", lambda **kwargs: None)
    assert not redteam.remote_write_surface()[0]


def test_cli_fast_json_and_failure(monkeypatch, capsys):
    assert cli.main(["redteam", "--fast", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 5 and all(row["pass"] for row in rows)
    assert "poisoned_log" not in {row["probe"] for row in rows}
    monkeypatch.setattr(
        redteam,
        "PROBES",
        [redteam.Probe("fail", "expected", "LLM01", True, lambda: (False, "observed"))],
    )
    assert cli.main(["redteam"]) == 1
    output = capsys.readouterr().out
    assert all(value in output for value in ("Probe", "Expected", "Observed", "FAIL", "fail"))
