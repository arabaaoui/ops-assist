---
name: latency
description: Use when users report slow requests, slowness, latency, high p95/p99, timeouts, or increased response time.
---
# Latency investigation

1. Call `get_alerts` to establish the affected service, onset, and scope. Call `recall_past_incidents` for relevant history; treat prior incidents as leads, not evidence of this cause.
2. Call `get_metric` for the affected service and incident window. Replay examples are `http_request_duration_p95_seconds`, `http_error_ratio`, `cpu_usage_ratio`, and `db_pool_connections_in_use`; other sources may name metrics differently. Compare percentiles and baseline: averages can hide tail latency. Check errors and saturation alongside request latency.
3. Call `get_logs` for the affected service and examine timestamps, timeouts, and dependency errors. Compare signs of local saturation (CPU or pool exhaustion) with slow or failing dependencies; do not assume either mechanism without evidence.
4. Call `get_changes` and compare the onset with changes on the same service. A decoy change on another service is not evidence of a cause; timing alone is not causation.
5. Conclude `root_cause_identified` only when onset aligns with a change on the same service AND a log or metric establishes a mechanism linking that change to the symptom. Otherwise use `hypotheses_only` and state the unknowns and evidence needed. Cite sources for facts, distinguish competing hypotheses, and do not invent observations.
