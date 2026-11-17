# Failure review: ops-assist

This review uses five common causes of project failure as a practical grid. Evidence shows what the repository implements; it does not establish production effectiveness. The data and examples are fictional.

## Unclear need

The intended outcome is to reduce time to diagnosis by collecting incident observations and producing a structured report; the [investigation loop](../src/ops_assist/run.py) and [end-to-end scripted test](../tests/test_agent_loop.py) demonstrate the workflow, not a measured reduction. Define a baseline and compare diagnosis times with and without the assistant before claiming an improvement.

## Missing data

The default [replay source](../src/ops_assist/observability/replay.py) supplies recorded incidents; optional [Prometheus](../src/ops_assist/observability/prometheus.py) and [Loki](../src/ops_assist/observability/loki.py) connectors provide live observations, while the [knowledge corpus](../src/ops_assist/data/knowledge/runbooks) supplies runbooks. [Source contract tests](../tests/contract.py) describe the expected interface. Check access, completeness and freshness for the actual incident before relying on these sources.

## No validation

The [security policy](../src/ops_assist/security.py) classifies one agent write, rollback, and requires human confirmation; [security tests](../tests/test_security.py) exercise approval and rejection. The [evaluation](../src/ops_assist/evaluation.py) scores reports, and [red-team probes](../src/ops_assist/redteam.py) exercise selected security boundaries. Run the following offline after dependencies are installed; these checks do not validate every real-model response or attack:

```bash
uv run --frozen ops-assist eval check-reports tests/fixtures/evaluation/passing
uv run --frozen ops-assist redteam --fast
```

## Uncontrolled cost

The [investigation trace](../src/ops_assist/run.py) records available input, cached input and output token counts per model response, with a bound and omission counter; [cost tests](../tests/test_cost.py) cover the offline estimator. The following command compares fictional per-incident scenarios, not measured investigation costs:

```bash
uv run --frozen ops-assist eval cost --json
```

For a measured investigation, `uv run --frozen ops-assist investigate "Why is the fictional service slow?" --show-context` requires a configured model and displays approximate request token counts, not provider usage. Reconcile provider usage and pricing or billing to determine cost per investigation; the Python investigation trace retains available per-response usage. Missing usage, omitted entries, cache pricing and other fees can prevent a complete figure. The project does not currently calculate or enforce an actual monetary cost per investigation; establish a budget and reconcile it before deployment. The [CLI](../src/ops_assist/cli.py) and [run implementation](../src/ops_assist/run.py) define the available output.

## No owner

Owner: ____________________

The owner is intentionally unassigned. Assign a person accountable for the dataset, validation schedule, cost budget and incident workflow; the repository's [evaluation dataset](../src/ops_assist/data/eval/dataset.yaml) and [release threshold](../src/ops_assist/evals/threshold.yaml) need an accountable maintainer.

## Recommendations and roadmap

- Before deployment, assign the owner and agree on a diagnosis-time baseline and target.
- Before deployment, verify data access and freshness, set a budget and reconcile actual per-investigation costs.
- At each change, run the offline evaluation and red-team checks; periodically validate with representative incidents and the selected model under an approved budget.
