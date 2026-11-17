---
id: payments-db
title: Payments database saturation
service: payments-db
updated: 2026-03-01
owner: operations
---

## Observation
A saturated payments database can increase connection wait time for payment-api.

## Response
Inspect active connections and database latency before changing pool limits.
