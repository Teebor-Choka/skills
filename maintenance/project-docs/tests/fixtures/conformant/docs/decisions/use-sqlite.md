---
title: Use SQLite for the store
status: accepted
project: widgetd
updated: 2026-10-13
---

# Use SQLite for the store

**Context.** widgetd runs as a single node and must survive a restart without losing events.
An external database would add an operational dependency the deployment does not want.

**Decision.** Store events in an embedded SQLite database on local disk, written synchronously
on the request path [^pg].

**Consequences.** Durable within the node, no network dependency. Throughput is bounded by local
disk; horizontal scaling would need a different store.

[^pg]:
    Postgres was considered and dropped: it adds a server to run and secure for no gain at
    single-node scale. Revisit if widgetd ever needs to scale out.
