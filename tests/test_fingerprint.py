import json
from dataclasses import replace
from pathlib import Path

from ops_assist import cli
from ops_assist import fingerprint as fp
from ops_assist.config import load_settings
from ops_assist.knowledge.living import save_report
from ops_assist.report import IncidentReport

ROOT = Path(__file__).resolve().parents[1]


def test_stable_and_each_input_changes(monkeypatch, tmp_path):
    package = tmp_path / "package"
    (package / "prompts").mkdir(parents=True)
    (package / "skills" / "example").mkdir(parents=True)
    prompt = package / "prompts" / "example.md"
    skill = package / "skills" / "example" / "SKILL.md"
    prompt.write_text("prompt")
    skill.write_text("skill")
    agent = package / "agent.py"
    agent.write_text("EXPERT_INSTRUCTION = 'x'")
    monkeypatch.setattr(fp, "PACKAGE", package)
    monkeypatch.delenv("OPS_ASSIST_TOPOLOGY", raising=False)
    settings = load_settings({})
    original = fp.fingerprint(settings)
    assert fp.fingerprint(settings) == original
    assert fp.fingerprint(settings, topology="experts") != original
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    assert fp.fingerprint(settings) != original
    monkeypatch.delenv("OPS_ASSIST_TOPOLOGY")
    for path in (prompt, skill, agent):
        old = path.read_text()
        path.write_text(old + " changed")
        assert fp.fingerprint(settings) != original
        path.write_text(old)
    for changed in (
        replace(settings, profile="other"),
        replace(settings, models=["other"]),
        replace(settings, fast_models=["other"]),
        replace(settings, deterministic=True),
    ):
        assert fp.fingerprint(changed) != original
    monkeypatch.setattr(fp, "SCORER_VERSION", "2")
    assert fp.fingerprint(settings) != original
    monkeypatch.setattr(fp, "SCORER_VERSION", "1")
    monkeypatch.setattr(fp, "load_dataset", lambda: {"version": "99"})
    assert fp.fingerprint(settings) != original
    monkeypatch.setattr(fp, "load_dataset", lambda: {"version": "1.0.0"})
    before = fp.fingerprint(settings)
    monkeypatch.setattr(fp.IncidentReport, "model_json_schema", lambda: {"changed": True})
    assert fp.fingerprint(settings) != before


def test_secrets_and_endpoints_not_inputs(monkeypatch):
    settings = load_settings({})
    before = fp.fingerprint(settings)
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-secret")
    assert (
        fp.fingerprint(replace(settings, api_base="https://user:fictional-secret@host")) == before
    )
    assert "fictional-secret" not in before


def test_profile_and_report_fingerprint(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))
    settings = load_settings()
    assert cli.main(["profile"]) == 0
    assert f"Fingerprint: {fp.fingerprint(settings)}" in capsys.readouterr().out
    report = IncidentReport(summary="Unknown", status="insufficient_data")
    save_report(report, "session", settings=settings)
    files = list(tmp_path.rglob("last.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["fingerprint"] == fp.fingerprint(settings)


def test_latest_changelog_matches_default_fingerprint():
    latest = (ROOT / "BEHAVIOR_CHANGELOG.md").read_text().split("## ")[1]
    assert fp.fingerprint(load_settings({})) in latest
