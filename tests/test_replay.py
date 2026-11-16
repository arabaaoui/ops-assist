import json

import pytest
from contract import ObservationContract

from ops_assist.observability import (
    MAX_LOG_LINES,
    ObservationError,
    ReplaySource,
    list_incidents,
)


class TestReplayHonoursTheContract(ObservationContract):
    @pytest.fixture
    def source(self):
        return ReplaySource("payment-latency")

    @pytest.fixture
    def sample(self):
        return {
            "service": "payment-api",
            "metric": "http_request_duration_p95_seconds",
            "foreign_metric": "db_pool_connections_in_use",
            "unknown_metric": "nope",
        }


def test_the_bundled_incidents_are_listed():
    assert "payment-latency" in list_incidents()


def test_an_unknown_incident_is_refused():
    with pytest.raises(FileNotFoundError):
        ReplaySource("no-such-incident")


def test_incidents_can_live_outside_the_package(tmp_path, monkeypatch):
    (tmp_path / "mine").mkdir()
    (tmp_path / "mine" / "incident.json").write_text('{"fictional": true}')
    monkeypatch.setenv("OPS_ASSIST_INCIDENTS_DIR", str(tmp_path))
    assert list_incidents() == ["mine"]


def test_a_corrupt_recording_becomes_an_observation_error(tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "incident.json").write_text("{}")
    (tmp_path / "bad" / "alerts.json").write_text("{not json")
    source = ReplaySource("bad", root=tmp_path)
    with pytest.raises(ObservationError, match="not valid JSON"):
        source.alerts()
    (tmp_path / "bad" / "alerts.json").write_text("[]")
    with pytest.raises(ObservationError, match="no readable metrics.json"):
        source.changes("x")


def test_the_reference_incident_points_at_the_deployment_and_is_fictional():
    source = ReplaySource("payment-latency")
    assert source.incident["fictional"] is True
    assert source.changes("payment-api")[0]["id"] == "DEP-2140"


def test_the_reference_incident_contains_a_prompt_injection_in_its_logs():
    # Kept on purpose: the security chapter checks the agent ignores it.
    lines = ReplaySource("payment-latency").logs("payment-api", limit=200)
    assert any("IGNORE ALL PREVIOUS INSTRUCTIONS" in x["message"] for x in lines)


def test_every_bundled_incident_file_is_valid(incidents_dir):
    for d in incidents_dir.iterdir():
        for f in ("incident.json", "alerts.json", "metrics.json", "changes.json", "expected.json"):
            json.loads((d / f).read_text())


def _write(tmp_path, logs: list[dict], alerts: list | None = None):
    d = tmp_path / "synthetic"
    d.mkdir()
    (d / "incident.json").write_text('{"fictional": true}')
    (d / "alerts.json").write_text(json.dumps(alerts or []))
    (d / "metrics.json").write_text("[]")
    (d / "changes.json").write_text("[]")
    (d / "logs.jsonl").write_text("\n".join(json.dumps(x) for x in logs))
    return ReplaySource("synthetic", root=tmp_path)


def test_logs_are_capped_whatever_the_caller_asks(tmp_path):
    lines = [
        {"ts": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", "service": "s", "level": "info"}
        for i in range(250)
    ]
    out = _write(tmp_path, lines).logs("s", limit=10_000)
    assert len(out) == MAX_LOG_LINES
    assert out[0]["ts"] == "2026-01-01T00:04:09Z"  # the newest, not the first written


def test_an_incident_without_alerts_answers_an_empty_list(tmp_path):
    source = _write(tmp_path, [{"ts": "t", "service": "s", "level": "info"}])
    assert source.alerts() == []


def test_the_answer_key_is_never_loaded_by_the_source():
    source = ReplaySource("payment-latency")
    assert "root_cause" not in json.dumps(source.incident)
    assert (source.dir / "expected.json").is_file()
