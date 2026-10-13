---
title: PROJECT — agent instructions
project: PROJECT
updated: YYYY-MM-DD
---

# PROJECT — agent instructions

Single source of truth for AI coding agents (Claude Code reads this natively; Copilot and others
read it as `AGENTS.md`). Start in [`docs/`](docs/).

One or two lines on what the project is. This file points into `docs/`; it does not restate it.

## Read first

- [`docs/overview.md`](docs/overview.md) — purpose, layout, stack, how to build and run.
- [`docs/decisions/`](docs/decisions/) — why it is built this way (read before changing a
  load-bearing choice; the alternatives there were already set aside).
- [`docs/spec.md`](docs/spec.md) — the as-built behavior, if the project has one.

## Essentials

The few build/run/test commands an agent needs before touching anything. Keep it short; the detail
is in `docs/overview.md`.
