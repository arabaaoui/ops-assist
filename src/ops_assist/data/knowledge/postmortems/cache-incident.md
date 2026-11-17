---
id: cache-incident
title: Cache expiry surge
service: catalog-api
updated: 2026-01-15
owner: operations
---

## Observation
An expired hot key caused simultaneous cache misses and increased database load.

## Response
Request coalescing reduced the surge.
