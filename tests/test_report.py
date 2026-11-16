import pytest
from pydantic import ValidationError

from ops_assist.report import Fact, Hypothesis, IncidentReport, ProposedAction

FACT = Fact(statement="p95 latency tripled at 09:00", source="replay/metrics/p95")


def test_a_complete_report_validates():
    r = IncidentReport(
        summary="v2.14 exhausts the db pool.",
        status="root_cause_identified",
        facts=[FACT],
        hypotheses=[
            Hypothesis(
                statement="v2.14 adds a query per payment", confidence=0.8, supporting_facts=[0]
            )
        ],
        proposed_action=ProposedAction(
            kind="rollback_deployment", target="payment-api", reason="revert v2.14"
        ),
    )
    assert r.hypotheses[0].supporting_facts == [0]


def test_a_hypothesis_cannot_cite_a_missing_fact():
    with pytest.raises(ValidationError, match="missing facts"):
        IncidentReport(
            summary="x",
            status="hypotheses_only",
            facts=[FACT],
            hypotheses=[Hypothesis(statement="h", confidence=0.5, supporting_facts=[3])],
        )


def test_a_negative_index_does_not_cite_the_last_fact():
    with pytest.raises(ValidationError, match="missing facts"):
        IncidentReport(
            summary="x",
            status="hypotheses_only",
            facts=[FACT],
            hypotheses=[Hypothesis(statement="h", confidence=0.5, supporting_facts=[-1])],
        )


def test_no_root_cause_without_facts():
    with pytest.raises(ValidationError, match="without a single fact"):
        IncidentReport(summary="x", status="root_cause_identified")


def test_no_action_on_insufficient_data():
    with pytest.raises(ValidationError, match="insufficient data"):
        IncidentReport(
            summary="x",
            status="insufficient_data",
            proposed_action=ProposedAction(kind="rollback_deployment", target="a", reason="b"),
        )


def test_only_the_rollback_action_exists():
    with pytest.raises(ValidationError):
        ProposedAction(kind="delete_database", target="a", reason="b")


def test_no_action_without_a_hypothesis_backed_by_a_fact():
    with pytest.raises(ValidationError, match="backed by a fact"):
        IncidentReport(
            summary="x",
            status="hypotheses_only",
            proposed_action=ProposedAction(kind="rollback_deployment", target="a", reason="b"),
        )


def test_a_hypothesis_must_rest_on_at_least_one_fact():
    with pytest.raises(ValidationError):
        Hypothesis(statement="pure guess", confidence=0.1)
