---
id: pool-exhaustion
title: Database pool exhaustion
service: payment-api
updated: 2026-01-15
owner: operations
---

## Observation
Connection pool exhaustion causes requests to wait for database connections.

## Response
Inspect active connections, leaks and pool wait time. Reduce load before tuning limits.
