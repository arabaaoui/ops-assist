"""The incident report: the one structured output the agent must produce.

A report separates what was observed (facts, each with its source) from what is
inferred (hypotheses, each with a confidence) and from what is not known. An
agent that cannot conclude says so with ``status="insufficient_data"`` rather
than inventing a root cause.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
