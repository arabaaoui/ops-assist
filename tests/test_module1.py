import asyncio
import json
import re
from pathlib import Path

from test_agent_loop import ScriptedModel

from ops_assist import cli
from ops_assist.memory import list_memories, remember
from ops_assist.observability import ReplaySource
from ops_assist.report import IncidentReport
from ops_assist.run import investigate
from ops_assist.tools import make_tools
from ops_assist.triage import pretriage

ROOT = Path(__file__).resolve().parents[1]


def test_architecture_paths_exist():
    doc = (ROOT / "docs/architecture.md").read_text()
    paths = re.findall(r"`(src/[^`]+)`", doc)
    assert paths and all((ROOT / p).is_file() for p in paths)


def test_triage_and_cli(capsys):
    result = pretriage(ReplaySource("payment-latency"))
    assert result.affected_services == ["payment-api"]
    assert result.firing_alert_ids == ["ALR-1042", "ALR-1043"]
    assert result.earliest_since.isoformat() == "2026-03-12T09:02:00+00:00"
    assert [c["id"] for c in result.suspect_changes] == ["DEP-2140"]
    assert cli.main(["triage", "--incident", "payment-latency"]) == 0
    assert json.loads(capsys.readouterr().out)["suspect_changes"][0]["id"] == "DEP-2140"


def test_memory_redacts_and_forgets(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path))
    report = IncidentReport(
        summary="password=hunter2 token=abc a@example.org", status="insufficient_data"
    )
    remember(report, ["s", "other"])
    assert "hunter2" not in (tmp_path / "reports.jsonl").read_text()
    assert "abc" not in (tmp_path / "reports.jsonl").read_text()
    assert "a@example.org" not in (tmp_path / "reports.jsonl").read_text()
    assert cli.main(["memory", "list", "--service", "s"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert cli.main(["memory", "forget", "--service", "s"]) == 0
    assert [e["service"] for e in list_memories()] == ["other"]


def test_tools_cap_and_handle_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path))

    class Source:
        def metric(self, name, service):
            return {"points": [[i, 100 if i >= 35 else 0] for i in range(100)]}

        def logs(self, service, level, limit):
            return [{"message": "x" * 500}] * 250

        def changes(self, service):
            raise RuntimeError("private")

    _, metric, logs, changes, recall = [
        lambda *a, _f=f, **kw: asyncio.run(_f(*a, **kw)) for f in make_tools(Source())
    ]
    series = metric("m", "s")["metric"]
    assert series["summarised"] and len(series["points"]) == 10
    assert series["min"] == 0 and series["max"] == 100 and series["mean"] == 65
    assert series["first"] == [0, 0] and series["last"] == [99, 100]
    assert [35, 100] in series["points"]
    lines = logs("s", limit=1000)["logs"]
    assert len(lines) == 200 and len(lines[0]["message"]) == 300
    assert len(logs("s", limit=2)["logs"]) == 2
    assert logs("s", limit=0)["status"] == "error"
    assert changes("s")["status"] == "error"
    for i in range(12):
        remember(IncidentReport(summary=f"incident {i}", status="insufficient_data"), ["s"])
    assert [e["summary"] for e in recall("s")["incidents"]] == [
        f"incident {i}" for i in range(2, 12)
    ]


def test_investigation_saves_session_memory_and_context(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path / "memory"))
    report, trace = investigate("Why?", model=ScriptedModel(seen=[]), show_context=True)
    assert report.summary == list_memories("payment-api")[0]["summary"]
    assert len(trace.context_tokens) == 2 and trace.context_tokens[1] > trace.context_tokens[0]


def test_pretriage_reaches_model_and_context_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path))

    class CapturingModel(ScriptedModel):
        async def generate_content_async(self, llm_request, stream=False):
            contents = llm_request.model_dump_json()
            assert "<pretriage_data>" in contents
            assert "DEP-2140" in contents
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    def scripted(question, settings, show_context=False):
        return investigate(
            question, settings=settings, model=CapturingModel(seen=[]), show_context=show_context
        )

    monkeypatch.setattr(cli, "investigate", scripted)
    assert cli.main(["investigate", "Why?", "--show-context"]) == 0
    out = capsys.readouterr().out
    assert "Approximate tokens of the serialized request" in out
    assert re.search(r"\n\s*1\s+ops_assist\s+\d+", out)
