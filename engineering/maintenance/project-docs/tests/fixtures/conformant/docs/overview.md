---
title: widgetd — overview
kind: overview
project: widgetd
updated: 2026-10-13
---

# widgetd — overview

widgetd ingests widget events over HTTP and writes them to a local store. It talks to an
upstream metrics collector and a SQLite database.

## Layout

| Path    | Role                     |
| ------- | ------------------------ |
| `src/`  | daemon and HTTP handlers |
| `docs/` | repo documentation       |

## Stack

Rust, axum for HTTP, SQLite via rusqlite. Built with cargo.

## Build, run, deploy

`make build`, `make run`. Deploys as a single static binary to the fleet.

## Diagram

```mermaid
flowchart TD
    client[client] --> widgetd
    widgetd --> db[(SQLite)]
    widgetd --> metrics[metrics collector]
```

## Pointers

- Decisions: [`decisions/`](decisions/)
- Deep spec: [`spec.md`](spec.md)
