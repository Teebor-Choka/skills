---
name: graph-engine
description: Standalone work-division — given units with dependencies and write-sets, compute collision-free parallel waves, the critical path, barriers, and a suggested collaboration shape. The architect's graph step, usable on its own when a build is genuinely parallel.
disable-model-invocation: true
metadata:
  version: "1.0.0"
---

Reach for this when work is genuinely parallel — several components with **disjoint write-sets**, where
wall-clock actually matters — and you want the division without standing up a full architect package.
It is the same engine the `architect` skill runs at its graph step; this surfaces it for standalone use.

## Use it

Write a node spec (JSON): each unit's `id`, `deliverable`, `deps`, `write_set`, plus any `loops`, then
run the architect skill's graph script:

    python3 ~/.claude/skills/architect/scripts/graph.py spec.json

It computes the transitive-reduced parallel waves, the critical path, barrier nodes, and the
concurrency cap, and **detects write-set collisions within a wave** (two units touching the same
resource) — exiting non-zero on a cycle or a collision, a spec no fleet can run as written. Pick a
collaboration shape, and read the per-shape failure guards, in
`~/.claude/skills/architect/references/graph-patterns.md`.

## When not to

A single unit, or holistic work with no disjoint write-sets, has nothing to divide: the engine no-ops,
and a sequential pass is faster and simpler. And splitting is not free — when you dispatch the divided
work to parallel agents, follow it with a **serial integration pass** (isolated contexts don't
integrate themselves).

This is the on-demand splitting capability, reached for when the seam is real and wall-clock binds —
not a standing orchestration tier. (A measured baseline cut the standing fleet: parallelism's wall-clock
win didn't beat its token/integration cost for a solo operator. The engine is kept as a tool, not a layer.)

<!-- Harvested from the role-based-suite design baseline (decision D25a): the splitting function
     survives as an on-demand tool. The engine itself is the architect skill's scripts/graph.py —
     referenced here, not duplicated, so there is one copy to maintain. -->
