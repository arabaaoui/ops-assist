---
name: errors-5xx
description: Use for 5xx errors, 500/502/503/504 responses, a rising error rate, or failing requests.
---
# 5xx investigation

1. Call `get_alerts` to establish the affected service, onset, and scope. Call `recall_past_incidents` for relevant history; past incidents are leads, not evidence of this cause.
2. Call `get_metric` for the affected service and incident window. Replay examples are `http_error_ratio`, `http_request_duration_p95_seconds`, `cpu_usage_ratio`, and `db_pool_connections_in_use`; other sources may name metrics differently. Compare error rate and latency with baseline, distinguishing failing requests from total traffic; averages can hide tail latency.
3. Call `get_logs` for the affected service and inspect error codes, timestamps, and dependency failures. Compare local saturation (CPU or pool exhaustion) with dependency failure; require evidence for the mechanism.
4. Call `get_changes` and compare the onset with changes on the same service. A decoy change on another service is not evidence of a cause; timing alone is not causation.
5. Conclude `root_cause_identified` only when onset aligns with a change on the same service AND a log or metric establishes a mechanism linking that change to the errors. Otherwise use `hypotheses_only` and state the unknowns and evidence needed. Cite sources for facts, distinguish competing hypotheses, and do not invent observations.
