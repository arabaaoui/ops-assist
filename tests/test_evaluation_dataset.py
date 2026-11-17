import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from ops_assist import cli
from ops_assist.evaluation_dataset import DATA, PUBLISHED, checksum, load_dataset
from ops_assist.observability import ObservationError, ReplaySource, list_incidents


def test_dataset_schema_recordings_and_release_checksum():
    dataset = load_dataset()
    assert dataset["checksum"] == yaml.safe_load(PUBLISHED.read_text())[dataset["version"]]
    assert len(dataset["incidents"]) == 6
    assert {x["id"] for x in dataset["incidents"]} == set(list_incidents())
    for case in dataset["incidents"]:
        source = ReplaySource(case["id"])
        expected = json.loads((source.dir / "expected.json").read_text())
        assert set(expected) >= {
            "status",
            "root_cause_service",
            "root_cause_change",
            "answer",
            "required_facts_sources",
            "forbidden_conclusions",
        }
        assert expected["status"] in {
            "root_cause_identified",
            "hypotheses_only",
            "insufficient_data",
        }
        if case["id"] != "payment-latency":
            assert expected["status"] in expected["accepted_statuses"]
            assert set(expected["accepted_statuses"]) == {expected["status"]}
        assert expected["answer"] and expected["forbidden_conclusions"]
        assert source.incident["fictional"] is True
        alerts = source.alerts()
        assert alerts and all(
            {"id", "name", "service", "severity", "since", "source"} <= a.keys() for a in alerts
        )
        series = json.loads((source.dir / "metrics.json").read_text())
        for item in series:
            result = source.metric(item["name"], item["service"])
            assert result["points"] and result["unit"] and result["source"]
        service = alerts[0]["service"]
        assert source.logs(service) and source.logs(service)[0]["source"]
        changes = source.changes(service)
        assert all(c["source"] for c in changes)
        assert set(expected["required_facts_sources"]) <= {"alerts", "metrics", "logs", "changes"}
        if expected["status"] in {"insufficient_data", "hypotheses_only"}:
            assert expected["root_cause_service"] is None and expected["root_cause_change"] is None
            if expected["status"] == "hypotheses_only":
                assert expected["accepted_hypotheses"]
                assert all(
                    h["change"] in {c["id"] for c in changes}
                    for h in expected["accepted_hypotheses"]
                )
            else:
                assert expected["accepted_hypotheses"] == []
        else:
            assert expected["root_cause_service"] == service
            assert expected["root_cause_change"] in {c["id"] for c in changes}


def test_checksum_detects_case_and_recording_changes(tmp_path):
    shutil.copytree(DATA / "incidents", tmp_path / "incidents")
    data = load_dataset()
    data["incidents"][0]["question"] += " changed"
    assert checksum(data, tmp_path) != data["checksum"]
    data = load_dataset()
    path = tmp_path / "incidents" / data["incidents"][0]["id"] / "expected.json"
    path.write_text(path.read_text() + " ")
    assert checksum(data, tmp_path) != data["checksum"]
    manifest = tmp_path / "dataset.yaml"
    manifest.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(manifest, tmp_path)


@pytest.mark.parametrize(
    "mutation", ["version", "date", "changelog", "id", "question", "expected", "duplicate"]
)
def test_invalid_manifest_is_rejected(tmp_path, mutation):
    data = load_dataset()
    case = data["incidents"][0]
    if mutation == "version":
        data["version"] = "bad"
    if mutation == "date":
        data["created"] = "not-a-date"
    if mutation == "changelog":
        data["changelog"] = []
    if mutation == "id":
        case["id"] = "../escape"
    if mutation == "question":
        case["question"] = ""
    if mutation == "expected":
        case["expected"] = "/etc/passwd"
    if mutation == "duplicate":
        data["incidents"].append(case.copy())
    path = tmp_path / "dataset.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_dataset(path)


def test_no_evaluation_text_in_agent_content():
    root = Path(__file__).resolve().parents[1]
    directories = [
        DATA / "knowledge",
        root / "src/ops_assist/prompts",
        root / "src/ops_assist/skills",
        root / "examples",
    ]
    content = "\n".join(
        p.read_text(encoding="utf-8")
        for d in directories
        for p in d.rglob("*")
        if p.is_file() and p.suffix in {".md", ".yaml", ".json", ".py", ".txt"}
    ).casefold()
    for case in load_dataset()["incidents"]:
        expected = json.loads((DATA / "incidents" / case["id"] / "expected.json").read_text())
        for text in [
            case["question"],
            expected["answer"],
            *expected["forbidden_conclusions"],
            *(h["text"] for h in expected.get("accepted_hypotheses", [])),
        ]:
            assert text.casefold() not in content


def test_answer_key_is_not_a_replay_observation(tmp_path):
    source = ReplaySource("payment-latency")
    for name in ("expected.json", "../payment-latency/expected.json"):
        with pytest.raises(ObservationError):
            source._read(name)
    shutil.copytree(source.dir, tmp_path / "copy")
    (tmp_path / "copy" / "alerts.json").unlink()
    (tmp_path / "copy" / "alerts.json").symlink_to("expected.json")
    with pytest.raises(ObservationError):
        ReplaySource("copy", root=tmp_path).alerts()


def test_eval_list_is_offline_and_lists_all_cases(capsys):
    assert cli.main(["eval", "list"]) == 0
    output = capsys.readouterr().out
    data = load_dataset()
    assert data["version"] in output
    assert all(c["id"] in output and c["question"] in output for c in data["incidents"])
    assert "expected.json" not in output


def test_published_version_rejects_recomputed_checksum(tmp_path):
    shutil.copytree(DATA / "incidents", tmp_path / "incidents")
    data = load_dataset()
    data["incidents"][0]["question"] += " changed"
    data["checksum"] = checksum(data, tmp_path)
    path = tmp_path / "dataset.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="published dataset version has changed: bump the version"):
        load_dataset(path, tmp_path)
    data["version"] = "1.2.0"
    data["changelog"].append({"version": "1.2.0", "description": "Test revision"})
    data["checksum"] = checksum(data, tmp_path)
    path.write_text(yaml.safe_dump(data))
    assert load_dataset(path, tmp_path)["version"] == "1.2.0"


def test_published_history_is_preserved():
    published = yaml.safe_load(PUBLISHED.read_text())
    assert published["1.0.0"] == "0f083f6ae7ad3172e6cc61ca5fc6912a23bb2ee2a8b10c255c3e83bccd6cc826"
    assert published["1.1.0"] == "2441a928e338623a70080423bfa1192910851c5de9a21529f835271f5fb6ea8a"


def test_scenarios_require_combining_observations():
    deploy = ReplaySource("inc-2026-0412")
    assert deploy.metric("http_error_ratio", "checkout")["points"][1][1] > 0.5
    assert "build 2.1" in deploy.logs("checkout")[0]["message"]
    assert "build 2.1" in deploy.changes("checkout")[0]["summary"]
    cache = ReplaySource("inc-2026-0413")
    for name in ("cache_miss_ratio", "backend_read_requests_per_second"):
        points = cache.metric(name, "cache")["points"]
        assert points[1][1] > points[0][1]
    assert "fixed 300 seconds" in cache.changes("cache")[0]["summary"]
    assert "expired" in cache.logs("cache")[0]["message"]
    disk = ReplaySource("inc-2026-0415")
    for name in ("disk_usage_ratio", "database_log_directory_bytes"):
        points = disk.metric(name, "orders-db")["points"]
        assert points[1][1] > points[0][1]
    assert "retention increased" in disk.changes("orders-db")[0]["summary"]


def test_tls_metric_uses_consistent_ratio_and_neutral_identifiers():
    source = ReplaySource("inc-2026-0414")
    metric = source.metric("tls_failure_ratio", "auth-api")
    assert metric["unit"] == "ratio"
    assert all(0 <= value <= 1 for _, value in metric["points"])
    for ident in list_incidents():
        if ident != "payment-latency":
            assert re.fullmatch(r"inc-2026-04[0-9]{2}", ident)
            assert ReplaySource(ident).alerts()[0]["id"] == "ALR-" + ident


def test_abstention_is_the_expected_outcome_for_unproven_links():
    for number in range(12, 16):
        source = ReplaySource(f"inc-2026-04{number}")
        expected = json.loads((source.dir / "expected.json").read_text())
        assert expected["status"] == "hypotheses_only"
        assert "hypotheses_only" in expected["accepted_statuses"]
        assert "root_cause_identified" not in expected["accepted_statuses"]
        assert expected["accepted_hypotheses"][0]["text"]
    source = ReplaySource("inc-2026-0416")
    expected = json.loads((source.dir / "expected.json").read_text())
    assert expected["accepted_statuses"] == ["insufficient_data"]
    assert source.changes("payment-api") == []
