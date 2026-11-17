import json

import pytest

from ops_assist import cli
from ops_assist.feedback import collect, pairs
from ops_assist.knowledge.living import save_report
from ops_assist.report import IncidentReport
from ops_assist.security import StateStore


def report(summary):
    return IncidentReport(summary=summary, status="insufficient_data")


def test_feedback_last_pairs_and_redaction(capsys):
    save_report(report("First password=fictional"), "a", incident_id="case-a", question="Why?")
    assert cli.main(["feedback", "--report", "last", "--up", "--comment", "token=fictional"]) == 0
    capsys.readouterr()
    assert pairs() == []
    save_report(report("Second"), "b", incident_id="case-a", question="Why?")
    assert cli.main(["feedback", "--report", "last", "--down"]) == 0
    capsys.readouterr()
    assert cli.main(["feedback", "export", "--pairs"]) == 0
    output = capsys.readouterr().out
    pair = json.loads(output)
    assert pair["prompt"] == "Why?"
    assert "First" in pair["chosen"] and "Second" in pair["rejected"]
    assert "fictional" not in output
    store = StateStore()
    records = [
        json.loads(store.read_knowledge("feedback", n)) for n in store.list_knowledge("feedback")
    ]
    up = next(r for r in records if r["rating"] == "up")
    assert up["comment"] == "[redacted]" and up["report"]["summary"] == "First [redacted]"
    assert up["report_hash"].startswith("sha256:") and len(up["report_hash"]) == 71
    assert up["timestamp"].endswith("+00:00") and up["incident_id"] == "case-a"
    assert all(
        (store.root / "knowledge" / "feedback" / n).stat().st_mode & 0o777 == 0o600
        for n in store.list_knowledge("feedback")
    )


def test_explicit_reports_grouping_and_duplicates(tmp_path):
    path = tmp_path / "report.json"

    def add(summary, rating, incident="a", question="Why?"):
        path.write_text(
            json.dumps(
                {
                    "report": report(summary).model_dump(),
                    "incident_id": incident,
                    "question": question,
                }
            )
        )
        collect(str(path), rating)

    add("good", "up")
    add("good", "up")
    add("bad", "down", "b")
    add("bad", "down", "a", "Different?")
    add("good", "down")
    add("unknown", "down", None)
    add("secret one", "up", "token=one")
    add("secret two", "down", "token=two")
    add("secret question", "down", "a", "password=fictional")
    assert pairs() == []
    add("bad", "down")
    assert len(pairs()) == 1
    path.write_text(report("standalone").model_dump_json())
    collect(str(path), "down")
    assert len(pairs()) == 1


def test_contested_ratings_never_export_both_directions(tmp_path):
    path = tmp_path / "report.json"

    def add(summary, rating):
        path.write_text(
            json.dumps(
                {"report": report(summary).model_dump(), "incident_id": "a", "question": "Why?"}
            )
        )
        collect(str(path), rating)

    for summary in ("A", "B"):
        add(summary, "up")
        add(summary, "down")
    assert pairs() == []
    add("A", "up")
    assert pairs() == []
    add("B", "down")
    exported = pairs()
    assert len(exported) == 1
    assert '"A"' in exported[0]["chosen"] and '"B"' in exported[0]["rejected"]


def test_cli_validation_and_link_confinement(tmp_path, capsys):
    assert cli.main(["feedback", "--report", "last", "--up"]) == 1
    assert cli.main(["feedback", "export", "--pairs", "--up"]) == 1
    assert cli.main(["feedback", "--report", "last"]) == 1
    path = tmp_path / "report.json"
    path.write_text(report("safe").model_dump_json())
    link = tmp_path / "link.json"
    link.symlink_to(path)
    assert cli.main(["feedback", "--report", str(link), "--up"]) == 1
    with pytest.raises(ValueError):
        collect(str(path), "other")
    capsys.readouterr()
