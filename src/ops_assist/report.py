"""The incident report: the one structured output the agent must produce.

A report separates what was observed (facts, each with its source) from what is
inferred (hypotheses, each with a confidence) and from what is not known. An
agent that cannot conclude says so with ``status="insufficient_data"`` rather
than inventing a root cause.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Match identifiers embedded in prose as well as standalone source fields.
CHUNK_ID = re.compile(
    r"(?<![\w#])(?:runbook:|postmortem:)?[A-Za-z0-9_][A-Za-z0-9_.-]*#[0-9]+(?![\w#])"
)
OBSERVATION_SOURCE = re.compile(
    r"(?:^|/)(?:alerts|metrics|logs|changes)(?:/|$)|^get_(?:alerts|metric|logs|changes)(?:\b|:)"
)


def knowledge_citations(report: IncidentReport) -> set[str]:
    """Find chunk IDs in all report text, excluding generated warnings."""
    texts = [report.summary, *report.unknowns]
    texts.extend(value for fact in report.facts for value in (fact.statement, fact.source))
    texts.extend(hypothesis.statement for hypothesis in report.hypotheses)
    if report.proposed_action:
        texts.extend((report.proposed_action.target, report.proposed_action.reason))
    return {match.group() for text in texts for match in CHUNK_ID.finditer(text)}


def check_observation_support(report: IncidentReport) -> None:
    """Refuse a root cause unless each retained hypothesis cites an observation."""
    if report.status != "root_cause_identified":
        return
    if not report.hypotheses or any(
        not any(
            not CHUNK_ID.search(report.facts[i].source)
            and OBSERVATION_SOURCE.search(report.facts[i].source)
            for i in hypothesis.supporting_facts
        )
        for hypothesis in report.hypotheses
    ):
        raise ValueError("root cause requires observation support for each retained hypothesis")


class Fact(BaseModel):
    """Something observed in a tool result, never inferred."""

    statement: str = Field(description="What was observed, in one sentence.")
    source: str = Field(
        description="Where it was observed: tool name and the series, log or change id."
    )


class Hypothesis(BaseModel):
    """A possible explanation, backed by facts."""

    statement: str
    confidence: float = Field(ge=0.0, le=1.0, description="0 = pure guess, 1 = proven.")
    supporting_facts: list[int] = Field(
        min_length=1, description="Indexes into Report.facts that support this hypothesis."
    )


class ProposedAction(BaseModel):
    """An action the agent proposes; executing it always needs a human confirmation."""

    kind: Literal["rollback_deployment"]
    target: str = Field(description="Service whose last deployment would be rolled back.")
    reason: str


class IncidentReport(BaseModel):
    """What the agent hands back at the end of an investigation."""

    summary: str = Field(description="Two or three sentences a human on call can act on.")
    status: Literal["root_cause_identified", "hypotheses_only", "insufficient_data"]
    facts: list[Fact] = Field(default_factory=list)
    citation_warnings: list[str] = Field(
        default_factory=list,
        description="Knowledge citation and observation warnings set after investigation.",
    )
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    unknowns: list[str] = Field(
        default_factory=list, description="What would be needed to conclude."
    )
    proposed_action: ProposedAction | None = None

    @model_validator(mode="after")
    def _consistent(self) -> IncidentReport:
        for h in self.hypotheses:
            bad = [i for i in h.supporting_facts if not 0 <= i < len(self.facts)]
            if bad:
                raise ValueError(f"hypothesis cites missing facts {bad}: {h.statement!r}")
        if self.status == "root_cause_identified" and not self.facts:
            raise ValueError("a root cause cannot be identified without a single fact")
        if self.proposed_action is not None:
            if self.status == "insufficient_data":
                raise ValueError("no action can be proposed on insufficient data")
            if not self.hypotheses:
                raise ValueError(
                    "an action needs at least one hypothesis backed by a fact, whatever the status"
                )
        return self
