---
id: payment-pool-incident
title: Payment pool exhaustion
service: payment-api
updated: 2026-01-15
owner: operations
---

## Observation
Payment latency rose when database connection pool exhaustion caused requests to queue.

## Response
A connection leak depleted the pool. The team reduced load and repaired connection handling.
