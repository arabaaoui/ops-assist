---
id: cache-stampede
title: Cache stampede
service: catalog-api
updated: 2026-01-15
owner: operations
---

## Observation
A hot key expires and concurrent requests overwhelm the database.

## Response
Use request coalescing and staggered expiry after verifying cache misses.
