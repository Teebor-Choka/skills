---
name: graph-engine
description: Work-division engine — given units with dependencies and write-sets, compute collision-free parallel waves, the critical path, barriers, and a suggested collaboration shape. Self-contained (ships graph.py + the pattern catalog); the architect skill defers to it for its graph step.
disable-model-invocation: true
metadata:
  version: "1.0.0"
---

Reach for this when work is genuinely parallel — several components with **disjoint write-sets**, where
wall-clock actually matters — and you want the division. It ships the engine; the `decompose` skill
and the `architect` skill use it rather than bundling their own copy.

## Use it

Write a node spec (JSON): each unit's `id`, `deliverable`, `deps`, `write_set`, plus any `loops`, then
run the engine:

    python3 graph.py spec.json

It computes the transitive-reduced parallel waves, the critical path, barrier nodes, and the
concurrency cap, and **detects write-set collisions within a wave** (two units touching the same
resource) — exiting non-zero on a cycle or a collision, a spec no fleet can run as written. Pick a
collaboration shape, and read the per-shape failure guards, in `references/graph-patterns.md`.

## Tier the graph (cost + speed)

Give each node a `tier`, one of `reasoning` (design/synthesis/hard calls), `execution` (building, the
default), `light` (reads/extraction/validation/status), or `speed` (optional fast lane), and the
dispatcher runs each node on that model. This is where tiering pays off: the critical path's
design/synthesis nodes get Reasoning, the wide fan-out of readers/extractors/validators gets Light, and
the common waste (a fleet of Light reads running on a Reasoning model) disappears. A `speed`-lane node
uses the fast System-1 model where the harness configures one and falls back to Light where it does not,
so a latency-sensitive hot node is an optimization, not a hard dependency. Tier before you dispatch:
untiered defaults to Execution, which is right for builders but overpays for the readers.

## When not to

A single unit, or holistic work with no disjoint write-sets, has nothing to divide: the engine no-ops,
and a sequential pass is faster and simpler. And splitting is not free — when you dispatch the divided
work to parallel agents, follow it with a **serial integration pass** (isolated contexts don't
integrate themselves). This is an on-demand capability, reached for when the seam is real and wall-clock
binds — not a standing orchestration tier. (A measured baseline cut the standing fleet: parallelism's
wall-clock win didn't beat its token/integration cost for a solo operator. The engine is kept as a tool.)

<!-- The engine (graph.py) and the pattern catalog (references/graph-patterns.md) live here, extracted
     from the architect skill (PR review / decision D25a) so a general utility is not buried in one
     consumer. The architect skill references this skill lazily at its graph step. -->
