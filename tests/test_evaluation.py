import copy
import json
from collections.abc import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from ops_assist import cli
from ops_assist.config import load_settings
from ops_assist.evaluation import MAX_ERROR_LENGTH, evaluate, score_report
from ops_assist.evaluation_dataset import DATA

# Independent of expected.json: these are deliberately hand-authored incident answers.
CASES = {
    "payment-latency": (
        "root_cause_identified",
        "payment-api",
        "DEP-2140",
        ["alerts", "metrics", "logs", "changes"],
    ),
    "inc-2026-0412": ("hypotheses_only", "checkout", "DEP-2201", ["metrics", "changes"]),
    "inc-2026-0413": ("hypotheses_only", "cache", "CHG-2202", ["metrics", "changes"]),
    "inc-2026-0414": ("hypotheses_only", "auth-api", "CHG-2203", ["logs", "changes"]),
    "inc-2026-0415": ("hypotheses_only", "orders-db", "CHG-2204", ["metrics", "changes"]),
    "inc-2026-0416": (
        "insufficient_data",
        "payment-api",
        "DEP-9999",
        ["alerts", "metrics", "logs"],
    ),
}


QUESTIONS = {
    "Which evidence explains the payment slowdown in this recording?": "payment-latency",
    "What explains the checkout request failures in this recording?": "inc-2026-0412",
    "What explains the burst of backend reads in this recording?": "inc-2026-0413",
    "What interrupted secure connections in this recording?": "inc-2026-0414",
    "What prevented database writes in this recording?": "inc-2026-0415",
    "Can the intermittent payment failures be attributed to a specific cause?": "inc-2026-0416",
}


def report_for(incident, variant="correct"):
    status, service, change, sources = CASES[incident]
    statement = f"{service} and {change} may explain the incident."
    report = {
        "summary": "The evidence needs review.",
        "status": status,
        "facts": [{"statement": "Observed", "source": f"replay:{incident}/{s}"} for s in sources],
        "hypotheses": [{"statement": statement, "confidence": 0.7, "supporting_facts": [0]}],
        "unknowns": ["Further evidence is needed."],
    }
    if status == "insufficient_data":
        report["hypotheses"] = []
    if variant == "wrong":
        if status == "insufficient_data":
            report["unknowns"] = []
        else:
            report["hypotheses"][0]["statement"] = "Other service and DEP-9999 caused this."
    if variant == "negated":
        report["hypotheses"] = [
            {
                "statement": f"{service} and {change} were ruled out.",
                "confidence": 0.8,
                "supporting_facts": [0],
            }
        ]
    return report


class ScriptedEvaluation(BaseLlm):
    model: str = "scripted"
    variant: str = "correct"

    async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator:
        text = " ".join(p.text or "" for c in llm_request.contents for p in c.parts or [])
        ident = next(incident for question, incident in QUESTIONS.items() if question in text)
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=json.dumps(report_for(ident, self.variant)))]
            )
        )


@pytest.mark.parametrize("incident", CASES)
@pytest.mark.parametrize(
    "variant,passed", [("correct", True), ("wrong", False), ("negated", False)]
)
def test_independent_reports_against_each_key(incident, variant, passed):
    expected = json.loads((DATA / "incidents" / incident / "expected.json").read_text())
    assert all(score_report(report_for(incident, variant), expected).values()) is passed


def test_scripted_models_evaluate_all_cases_and_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_INCIDENTS_DIR", str(tmp_path / "other"))
    perfect, path = evaluate(load_settings(env={}), repeat=2, model=ScriptedEvaluation())
    from ops_assist.fingerprint import fingerprint

    assert perfect["fingerprint"] == fingerprint(load_settings({}))
    assert json.loads(path.read_text())["fingerprint"] == perfect["fingerprint"]
    assert len(perfect["results"]) == 12 and perfect["pass_rate"] == 1
    assert perfect["incident_pass_rates"] == dict.fromkeys(CASES, 1.0)
    assert json.loads(path.read_text()) == perfect
    assert all(r["report"] and r["error"] is None for r in perfect["results"])
    wrong, other = evaluate(load_settings(env={}), model=ScriptedEvaluation(variant="wrong"))
    assert wrong["pass_rate"] == 0
    assert path != other and other.parent == path.parent


def test_retained_hypothesis_and_sources():
    expected = json.loads((DATA / "incidents/payment-latency/expected.json").read_text())
    report = report_for("payment-latency")
    report["hypotheses"].append(
        {"statement": "other DEP-1", "confidence": 0.9, "supporting_facts": [0]}
    )
    assert not score_report(report, expected)["root_cause"]
    report["hypotheses"][1]["confidence"] = 0.1
    assert score_report(report, expected)["root_cause"]
    report["hypotheses"][0]["statement"] = "Another explanation. payment-api DEP-2140 was excluded."
    report["proposed_action"] = {
        "kind": "rollback_deployment",
        "target": "payment-api",
        "reason": "DEP-2140",
    }
    assert not score_report(report, expected)["root_cause"]
    report["facts"] = report["facts"][:1]
    assert not score_report(report, expected)["sources"]
    report["facts"] = []
    assert not score_report(report, expected)["valid"]


def test_hypotheses_and_abstention_constraints():
    expected = json.loads((DATA / "incidents/inc-2026-0412/expected.json").read_text())
    report = report_for("inc-2026-0412")
    report["status"] = "root_cause_identified"
    assert not score_report(report, expected)["status"]
    report["status"] = "hypotheses_only"
    report["hypotheses"] = []
    assert not score_report(report, expected)["root_cause"]
    report["status"] = "root_cause_identified"
    assert not score_report(report, expected)["valid"]
    expected = json.loads((DATA / "incidents/inc-2026-0416/expected.json").read_text())
    report = report_for("inc-2026-0416")
    report["hypotheses"] = [{"statement": "Unclear", "confidence": 0.5, "supporting_facts": [0]}]
    assert all(score_report(report, expected).values())
    report["hypotheses"][0]["confidence"] = 0.51
    assert not score_report(report, expected)["root_cause"]
    report["hypotheses"] = []
    report["unknowns"] = [" "]
    assert not score_report(report, expected)["root_cause"]


@pytest.mark.parametrize(
    "negation", ["not", "no", "ruled out", "excluded", "unlikely", "rather than", "instead of"]
)
def test_negation_does_not_affirm_expected_hypothesis(negation):
    expected = json.loads((DATA / "incidents/inc-2026-0412/expected.json").read_text())
    report = report_for("inc-2026-0412")
    report["hypotheses"][0]["statement"] = f"{negation} checkout DEP-2201."
    assert not score_report(report, expected)["root_cause"]


@pytest.mark.parametrize(
    "text,allowed",
    [
        ("The database host ran out of disk space.", False),
        ("THE DATABASE HOST RUNS OUT OF DISK SPACE.", False),
        ("The database host did not run out of disk space.", True),
        ("The database host ran out of disk space, ruled out.", True),
        (
            "The database host did not run out of disk space. "
            "The database host ran out of disk space.",
            False,
        ),
    ],
)
def test_forbidden_conclusions_by_sentence(text, allowed):
    expected = json.loads((DATA / "incidents/payment-latency/expected.json").read_text())
    report = report_for("payment-latency")
    report["summary"] = text
    assert score_report(report, expected)["forbidden"] is allowed
    report["summary"] = "Neutral."
    report["hypotheses"][0]["statement"] += " " + text
    assert score_report(report, expected)["forbidden"] is allowed


def test_cli_profile_repeat_and_show_reports(monkeypatch, capsys, tmp_path):
    seen = []

    def fake(settings, repeat):
        seen.append((settings.profile, repeat))
        return {
            "results": [
                {
                    "incident": "fictional",
                    "iteration": 1,
                    "checks": {"valid": False},
                    "passed": False,
                    "report": {"summary": "visible report"},
                    "error": "visible error",
                }
            ],
            "pass_rate": 0,
        }, tmp_path / "result.json"

    monkeypatch.setattr("ops_assist.evaluation.evaluate", fake)
    assert cli.main(["eval", "run", "--profile", "local", "--repeat", "2"]) == 0
    output = capsys.readouterr().out
    assert seen == [("local", 2)] and "FAIL" in output and "0.0%" in output
    assert "visible report" not in output and "visible error" not in output
    assert cli.main(["eval", "run", "--show-reports"]) == 0
    output = capsys.readouterr().out
    assert "visible report" in output and "visible error" in output
    assert cli.main(["eval", "run", "--profile", "missing"]) == 1
    with pytest.raises(ValueError, match="repeat"):
        evaluate(load_settings(env={}), 0)


def test_report_and_error_are_redacted_and_error_bounded(monkeypatch):
    from ops_assist.report import IncidentReport

    calls = []
    report = report_for("payment-latency")
    report["summary"] = "Contact person@example.test bearer sk-abcdefghijk"

    def investigate(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return IncidentReport.model_validate(copy.deepcopy(report)), None
        raise ValueError("password=hidden " + "x" * 1000)

    monkeypatch.setattr("ops_assist.evaluation.investigate", investigate)
    result, path = evaluate(load_settings(env={}))
    stored = json.loads(path.read_text())
    assert stored == result
    assert "person@example.test" not in path.read_text() and "hidden" not in path.read_text()
    assert "[redacted]" in result["results"][0]["report"]["summary"]
    assert result["results"][1]["error"].startswith("ValueError: [redacted]")
    assert len(result["results"][1]["error"]) == MAX_ERROR_LENGTH
    assert result["results"][1]["report"] is None and not result["results"][1]["passed"]
    assert all(c["allow_writes"] is False and c["save_memory"] is False for c in calls)
    assert all(c["settings"].session_db is None for c in calls)


def test_hypotheses_only_uses_highest_confidence_and_ties():
    expected = json.loads((DATA / "incidents/inc-2026-0412/expected.json").read_text())
    report = report_for("inc-2026-0412")
    report["hypotheses"][0]["confidence"] = 0
    report["hypotheses"].append(
        {"statement": "wrong cause", "confidence": 1, "supporting_facts": [0]}
    )
    assert not score_report(report, expected)["root_cause"]
    report["hypotheses"][0]["confidence"] = 1
    assert score_report(report, expected)["root_cause"]


@pytest.mark.parametrize("incident", ["payment-latency", "inc-2026-0412"])
@pytest.mark.parametrize(
    "contradiction",
    [
        "The service {service} was not involved.",
        "{change} was excluded.",
        "Ruled out.",
        "Excluded.",
    ],
)
def test_credited_statement_rejects_contradictions(incident, contradiction):
    expected = json.loads((DATA / "incidents" / incident / "expected.json").read_text())
    report = report_for(incident)
    _, service, change, _ = CASES[incident]
    report["hypotheses"][0]["statement"] += " " + contradiction.format(
        service=service, change=change
    )
    assert not score_report(report, expected)["root_cause"]


def test_forbidden_negation_must_be_local():
    expected = json.loads((DATA / "incidents/payment-latency/expected.json").read_text())
    report = report_for("payment-latency")
    report["summary"] = "The database host ran out of disk space without warning."
    assert not score_report(report, expected)["forbidden"]


@pytest.mark.parametrize(
    "text,affirmed",
    [
        ("not a b c database failure", False),
        ("not a b c d database failure", True),
        ("database failure a b ruled out", False),
        ("database failure a b c ruled out", True),
        ("database failure without warning", True),
        ("database failure was excluded", False),
    ],
)
def test_forbidden_phrase_negation_window(text, affirmed):
    from ops_assist.evaluation import _forbidden_affirmed

    assert _forbidden_affirmed(text, "database failure") is affirmed


def test_pass_rates_weight_all_repetitions():
    from ops_assist.evaluation import pass_rates

    overall, rates = pass_rates(
        [
            {"incident": "a", "passed": True},
            {"incident": "a", "passed": False},
            {"incident": "b", "passed": True},
        ]
    )
    assert overall == 2 / 3 and rates == {"a": 0.5, "b": 1}
    with pytest.raises(ValueError):
        pass_rates([])


def test_release_gate_and_policy(tmp_path):
    from ops_assist.evaluation import gate, load_threshold

    policy = load_threshold()
    assert policy["dataset_version"] == "1.1.0" and policy["justification"].strip()
    result = {"dataset_version": "1.1.0", "pass_rate": policy["value"]}
    assert gate(result, policy)
    assert not gate({**result, "pass_rate": policy["value"] - 0.01}, policy)
    assert not gate({**result, "dataset_version": "9.0.0"}, policy)
    path = tmp_path / "policy.yaml"
    path.write_text("value: 2\ndataset_version: 1.1.0\njustification: why\n")
    with pytest.raises(ValueError, match="threshold"):
        load_threshold(path)


def test_cli_gate_and_report_checks(monkeypatch, tmp_path, capsys):
    from pathlib import Path

    from ops_assist.evaluation import check_reports

    fixtures = Path(__file__).parent / "fixtures/evaluation"
    monkeypatch.setattr("ops_assist.evaluation.investigate", lambda *a, **k: pytest.fail("online"))
    assert cli.main(["eval", "check-reports", str(fixtures / "passing")]) == 0
    assert "100.0%" in capsys.readouterr().out
    assert cli.main(["eval", "check-reports", str(fixtures / "failing")]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert cli.main(["eval", "check-reports", str(tmp_path)]) == 1
    (tmp_path / "envelope.json").write_text(
        json.dumps({"incident_id": "payment-latency", "report": report_for("payment-latency")})
    )
    assert check_reports(tmp_path)["pass_rate"] == 1
    (tmp_path / "invalid.json").write_text("{")
    assert check_reports(tmp_path)["pass_rate"] == 0.5
    (tmp_path / "unknown.json").write_text('{"incident_id":"unknown"}')
    assert check_reports(tmp_path)["pass_rate"] == 1 / 3

    def fake(settings, repeat):
        return {
            "dataset_version": "1.1.0",
            "pass_rate": fake.rate,
            "results": [],
            "incident_pass_rates": {},
        }, tmp_path / "result"

    fake.rate = 0.8
    monkeypatch.setattr("ops_assist.evaluation.evaluate", fake)
    assert cli.main(["eval", "run", "--gate"]) == 0
    fake.rate = 0.79
    assert cli.main(["eval", "run", "--gate"]) == 1
    monkeypatch.setattr(
        "ops_assist.evaluation.load_threshold",
        lambda: {"dataset_version": "9.0.0", "value": 0, "justification": "test"},
    )
    assert cli.main(["eval", "run", "--gate"]) == 1


def test_compare_tiers_gate_requires_both(monkeypatch, tmp_path, capsys):
    def result(rate):
        return {
            "dataset_version": "1.1.0",
            "pass_rate": rate,
            "incident_pass_rates": {"x": rate},
            "total_tokens": 0,
            "approximate_calls": 0,
            "unknown_calls": 0,
            "duration_seconds": 0,
            "results": [],
        }, tmp_path / "result"

    monkeypatch.setattr(
        "ops_assist.evaluation.evaluate_tiers", lambda *a: {"main": result(1), "fast": result(0.5)}
    )
    assert cli.main(["eval", "run", "--compare-tiers", "--gate"]) == 1
    assert "x: 50.0%" in capsys.readouterr().out
    assert cli.main(["eval", "run", "--compare-tiers"]) == 0
