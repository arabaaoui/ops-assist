# ADR 0001: deterministic pre-triage before investigation

## Context

A fictional incident contains alerts and changes. Operators need a reproducible initial selection while retaining the ability to investigate evidence beyond fixed rules.

## Options

- A single prompt is simple but depends on a model even for mechanical filtering.
- A deterministic workflow is reproducible and inexpensive but cannot explore an unexpected cause.
- An agent can explore evidence but adds model cost and variable decisions.
- Multiple agents add coordination and context overhead without a demonstrated need here.

## Decision

Run a model-free pre-triage first, then pass its result as untrusted data to the investigation agent. Sort services by maximum alert severity and select changes of affected services in the 60 minutes before each service's earliest alert. A candidate is not proof of causation.

## Consequences

The first selection is testable and available offline. The agent can inspect metrics, logs and changes, at the cost of model calls. A fixed time window can miss relevant changes or include unrelated ones; the report must cite evidence and acknowledge uncertainty. Revisit the rule when real observations and evaluations justify it.
