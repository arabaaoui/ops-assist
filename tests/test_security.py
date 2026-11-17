"""Offline tests of the ADK security boundary and human confirmation."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from ops_assist.agent import build_agent
from ops_assist.config import load_settings
from ops_assist.observability import ReplaySource
from ops_assist.security import SecurityBoundary, make_rollback_tool
from ops_assist.tools import make_tools


class AttackModel(BaseLlm):
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if not responses:
            call = types.FunctionCall(name="get_logs", args={"service": "payment-api"})
        elif responses[-1].name == "get_logs":
            assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in str(responses[-1].response)
            call = types.FunctionCall(
                name="rollback_deployment",
                args={"service": "payment-api", "deployment_id": "DEP-2140"},
            )
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=json.dumps(
                                {
                                    "summary": "done",
                                    "status": "hypotheses_only",
                                    "facts": [],
                                    "hypotheses": [],
                                    "unknowns": ["cause"],
                                }
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(function_call=call)])
        )


def read_audit(monkeypatch):
    import os

    return [
        json.loads(line)
        for line in (Path(os.environ["OPS_ASSIST_STATE_DIR"]) / "audit.jsonl")
        .read_text()
        .splitlines()
    ]


def run_attack(source, *, approval=None, demo_client=None):
    boundary = SecurityBoundary()
    tools = make_tools(ReplaySource("payment-latency"))
    tools.append(make_rollback_tool(source, demo_client=demo_client, boundary=boundary))
    agent = Agent(
        name="test",
        model=AttackModel(),
        tools=tools,
        before_tool_callback=boundary.before,
        after_tool_callback=boundary.after,
        on_tool_error_callback=boundary.error,
    )
    runner = InMemoryRunner(agent=agent, app_name="test")

    async def go():
        session = await runner.session_service.create_session(app_name="test", user_id="u")

        async def execute(message):
            return [
                event
                async for event in runner.run_async(
                    user_id="u", session_id=session.id, new_message=message
                )
            ]

        events = await execute(types.Content(role="user", parts=[types.Part(text="Investigate")]))
        requests = [
            fc
            for ev in events
            for fc in ev.get_function_calls()
            if fc.name == "adk_request_confirmation"
        ]
        if approval is not None:
            assert len(requests) == 1
            response = types.FunctionResponse(
                id=requests[0].id, name=requests[0].name, response={"confirmed": approval}
            )
            events += await execute(
                types.Content(role="user", parts=[types.Part(function_response=response)])
            )
        await runner.close()
        return events, requests

    return asyncio.run(go())


def test_trapped_log_cannot_execute_without_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    events, requests = run_attack(ReplaySource("payment-latency"))
    assert requests and requests[0].args["originalFunctionCall"]["name"] == "rollback_deployment"
    assert not (tmp_path / "state/incident-state.json").exists()
    audit = read_audit(monkeypatch)
    assert [(e["tool"], e["outcome"]) for e in audit] == [
        ("get_logs", "ok"),
        ("rollback_deployment", "denied"),
    ]


def test_confirmed_replay_changes_only_simulated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    source = ReplaySource("payment-latency")
    before = (source.dir / "changes.json").read_bytes()
    run_attack(source, approval=True)
    state = json.loads((tmp_path / "state/incident-state.json").read_text())
    assert state[source.name]["payment-api"] == {"deployment_id": "DEP-2140", "version": "v2.13"}
    assert (source.dir / "changes.json").read_bytes() == before
    assert read_audit(monkeypatch)[-1]["outcome"] == "ok"


def test_rejected_confirmation_does_not_change_state(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    run_attack(ReplaySource("payment-latency"), approval=False)
    assert not (tmp_path / "state/incident-state.json").exists()
    assert read_audit(monkeypatch)[-1]["outcome"] == "denied"


@pytest.mark.parametrize("mode", ["demo", "live"])
def test_confirmed_non_replay_modes(monkeypatch, mode):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    calls = []
    client = SimpleNamespace(rollback_deployment=lambda *a: calls.append(a) or {"status": "ok"})
    run_attack(SimpleNamespace(name=mode), approval=True, demo_client=client)
    assert calls == ([("payment-api", "DEP-2140")] if mode == "demo" else [])
    assert read_audit(monkeypatch)[-1]["outcome"] == ("ok" if mode == "demo" else "denied")


def test_demo_without_client_is_unavailable(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    events, _ = run_attack(SimpleNamespace(name="demo"), approval=True)
    assert "not available offline" in str(events)
    assert read_audit(monkeypatch)[-1]["outcome"] == "failed"


def test_boundary_limits_redaction_and_unknown_write(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_MAX_TOOL_CALLS", "2")
    monkeypatch.setenv("OPS_ASSIST_MAX_DELEGATIONS", "1")
    policy = SecurityBoundary()
    context = SimpleNamespace(invocation_id="run")
    tool = SimpleNamespace(name="metrics_expert")
    args = {"api_key": "sensitive", "nested": ["password=secret"]}
    assert policy.before(tool, args, context) is None
    policy.after(tool, args, context, {"status": "ok"})
    result = policy.before(tool, args, context)
    assert result["reason"] == "delegation_limit"
    policy.after(tool, args, context, result)
    result = policy.before(tool, args, context)
    assert result["reason"] == "tool_call_limit"
    policy.after(tool, args, context, result)
    unknown = SimpleNamespace(name="new_tool")
    other = SimpleNamespace(invocation_id="another")
    result = policy.before(unknown, args, other)
    assert result["reason"] == "read_only"
    policy.after(unknown, args, other, result)
    audit = read_audit(monkeypatch)
    assert [a["outcome"] for a in audit] == ["ok", "denied", "denied", "denied"]
    assert "sensitive" not in str(audit) and "password=secret" not in str(audit)
    assert all(a["duration_ms"] >= 0 for a in audit)


def test_default_agent_is_read_only_and_limits_are_validated(monkeypatch):
    agent = build_agent(load_settings(env={}))
    assert not any(getattr(tool, "name", "") == "rollback_deployment" for tool in agent.tools)
    monkeypatch.setenv("OPS_ASSIST_MAX_TOOL_CALLS", "0")
    with pytest.raises(ValueError, match="OPS_ASSIST_MAX_TOOL_CALLS"):
        build_agent(load_settings(env={}))


def test_investigate_resumes_with_human_confirmation(monkeypatch, tmp_path):
    from ops_assist.run import investigate

    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    decisions = []
    report, trace = investigate(
        "Investigate",
        model=AttackModel(),
        confirm_tool=lambda name, args: decisions.append((name, args)) or True,
    )
    assert report.summary == "done"
    assert decisions == [
        ("rollback_deployment", {"service": "payment-api", "deployment_id": "DEP-2140"})
    ]
    assert [call.name for call in trace] == ["get_logs", "rollback_deployment"]
    assert (tmp_path / "state/incident-state.json").exists()


def test_cli_prompts_for_explicit_yes(monkeypatch, capsys):
    from ops_assist import cli
    from ops_assist.report import IncidentReport
    from ops_assist.run import InvestigationTrace

    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")

    def fake(question, settings, confirm_tool):
        assert confirm_tool("rollback_deployment", {"service": "payment-api"})
        return IncidentReport(
            summary="done", status="hypotheses_only", facts=[], hypotheses=[], unknowns=["cause"]
        ), InvestigationTrace()

    monkeypatch.setattr(cli, "investigate", fake)
    assert cli.main(["investigate", "why?"]) == 0
    assert "Confirmation required: rollback_deployment" in capsys.readouterr().out


def test_invalid_limits_and_audit_open_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_MAX_DELEGATIONS", "-1")
    with pytest.raises(ValueError, match="OPS_ASSIST_MAX_DELEGATIONS"):
        SecurityBoundary()
    monkeypatch.setenv("OPS_ASSIST_MAX_DELEGATIONS", "1")
    monkeypatch.setenv("OPS_ASSIST_AUDIT_FILE", str(tmp_path))
    with pytest.raises(ValueError, match="plain name"):
        SecurityBoundary()


def test_state_directory_cannot_be_recording(monkeypatch):
    source = ReplaySource("payment-latency")
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(source.dir))
    with pytest.raises(ValueError, match="overlaps installed package"):
        SecurityBoundary()


def test_budget_denial_in_actual_adk_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    monkeypatch.setenv("OPS_ASSIST_MAX_TOOL_CALLS", "1")
    events, requests = run_attack(ReplaySource("payment-latency"))
    assert not requests
    assert "tool_call_limit" in str(events)
    assert not (tmp_path / "state/incident-state.json").exists()
    assert [a["outcome"] for a in read_audit(monkeypatch)] == ["ok", "denied"]


def test_callbacks_are_installed_on_coordinator_and_experts(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    agent = build_agent(load_settings(env={}))
    for candidate in [agent, *agent.sub_agents]:
        assert candidate.before_tool_callback.__self__ is agent.before_tool_callback.__self__
        assert candidate.after_tool_callback.__self__ is agent.before_tool_callback.__self__
        assert candidate.on_tool_error_callback.__self__ is agent.before_tool_callback.__self__


def test_audit_default_permissions_and_unsafe_destinations(monkeypatch, tmp_path):
    import os
    import stat

    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    policy = SecurityBoundary()
    assert policy.audit_path == root / "audit.jsonl"
    policy.audit("get_logs", {}, "ok", 0)
    assert stat.S_IMODE(policy.audit_path.stat().st_mode) == 0o600
    target = root / "target"
    target.write_text("untouched")
    (root / "audit.jsonl").unlink()
    (root / "audit.jsonl").symlink_to(target)
    with pytest.raises(OSError):
        policy.audit("get_logs", {}, "ok", 0)
    assert target.read_text() == "untouched"
    (root / "audit.jsonl").unlink()
    os.link(target, root / "audit.jsonl")
    with pytest.raises(ValueError, match="hard links"):
        policy.audit("get_logs", {}, "ok", 0)
    (root / "audit.jsonl").unlink()
    (root / "audit.jsonl").write_text("")
    monkeypatch.setattr(os, "getuid", lambda: target.stat().st_uid + 1)
    with pytest.raises(ValueError, match="owned by the current user"):
        policy.audit("get_logs", {}, "ok", 0)
    assert target.read_text() == "untouched"


@pytest.mark.parametrize("relative", ["same", "ancestor", "descendant"])
def test_state_rejects_package_overlap(monkeypatch, relative):
    from ops_assist.security import PACKAGE_DIR, state_root

    path = {
        "same": PACKAGE_DIR,
        "ancestor": PACKAGE_DIR.parent,
        "descendant": PACKAGE_DIR / "data",
    }[relative]
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(path))
    with pytest.raises(ValueError, match="overlaps installed package"):
        state_root()


def test_state_rejects_symlink_and_wrong_owner(monkeypatch, tmp_path):
    import os

    from ops_assist.security import state_root

    root = tmp_path / "owned"
    root.mkdir()
    link = tmp_path / "state-link"
    link.symlink_to(root, target_is_directory=True)
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(link / "child"))
    with pytest.raises(ValueError, match="symlinks"):
        state_root()
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(root))
    monkeypatch.setattr(os, "getuid", lambda: root.stat().st_uid + 1)
    with pytest.raises(ValueError, match="owned by the current user"):
        state_root()


def test_pending_is_durable_before_action_and_redacted(monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    syncs = []
    original_sync = os.fsync

    def sync(fd):
        syncs.append(fd)
        original_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    run_attack(ReplaySource("payment-latency"), approval=True)
    audit = read_audit(monkeypatch)
    assert [entry["outcome"] for entry in audit] == ["ok", "denied", "pending", "ok"]
    assert syncs
    assert (tmp_path / "state/incident-state.json").exists()
    policy = SecurityBoundary()
    policy.audit("rollback_deployment", {"password": "sensitive"}, "pending", 0)
    assert "sensitive" not in policy.audit_path.read_text()


def test_failed_pending_audit_prevents_state_change(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    original = SecurityBoundary.audit

    def fail_pending(self, tool, args, outcome, started):
        if outcome == "pending":
            raise OSError("disk full")
        return original(self, tool, args, outcome, started)

    monkeypatch.setattr(SecurityBoundary, "audit", fail_pending)
    events, _ = run_attack(ReplaySource("payment-latency"), approval=True)
    assert "audit_unavailable" in str(events)
    assert not (tmp_path / "state/incident-state.json").exists()


def test_budget_survives_adk_confirmation_resume(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    monkeypatch.setenv("OPS_ASSIST_MAX_TOOL_CALLS", "2")
    events, requests = run_attack(ReplaySource("payment-latency"), approval=True)
    assert requests and "tool_call_limit" in str(events)
    assert not (tmp_path / "state/incident-state.json").exists()
    assert [entry["outcome"] for entry in read_audit(monkeypatch)] == ["ok", "denied", "denied"]


def test_default_audit_validates_state_root(monkeypatch, tmp_path):
    monkeypatch.delenv("OPS_ASSIST_AUDIT_FILE", raising=False)
    link = tmp_path / "state-link"
    target = tmp_path / "real-state"
    target.mkdir()
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(link))
    policy = SecurityBoundary()
    with pytest.raises(ValueError, match="symlinks"):
        policy.audit("get_logs", {}, "ok", 0)
    assert not (target / "audit.jsonl").exists()


def test_rejects_group_writable_root(monkeypatch, tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    root.chmod(0o720)
    with pytest.raises(ValueError, match="group or world writable"):
        SecurityBoundary().audit("get_logs", {}, "ok", 0)


def test_existing_audit_is_made_private(monkeypatch, tmp_path):
    import stat

    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    audit = root / "audit.jsonl"
    audit.write_text("")
    audit.chmod(0o644)
    SecurityBoundary().audit("get_logs", {}, "ok", 0)
    assert stat.S_IMODE(audit.stat().st_mode) == 0o600


def test_state_hard_link_is_refused(monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    target = root / "other"
    target.write_text("{}")
    os.link(target, root / "incident-state.json")
    events, _ = run_attack(ReplaySource("payment-latency"), approval=True)
    assert "hard links" in str(events)
    assert target.read_text() == "{}"
    assert read_audit(monkeypatch)[-1]["outcome"] == "denied"


def test_anchored_directory_survives_path_replacement(monkeypatch, tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    policy = SecurityBoundary()
    policy.audit("get_logs", {}, "ok", 0)
    original = tmp_path / "original"
    root.rename(original)
    root.mkdir(mode=0o700)
    policy.audit("get_logs", {}, "ok", 0)
    assert len((original / "audit.jsonl").read_text().splitlines()) == 2
    assert not (root / "audit.jsonl").exists()
    policy.store.update_state(ReplaySource("payment-latency"), "payment-api", "DEP-2140", "v2.13")
    assert (
        json.loads((original / "incident-state.json").read_text())["replay:payment-latency"][
            "payment-api"
        ]["version"]
        == "v2.13"
    )
    assert not (root / "incident-state.json").exists()
