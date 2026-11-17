---
id: payment-processor-incident
title: Payment processor timeouts
service: payment-api
updated: 2026-01-15
owner: operations
---

## Observation
Payment latency and timeouts increased when the external card processor stopped responding.

## Response
The processor restored its service; payment requests recovered without changes to the database pool.
