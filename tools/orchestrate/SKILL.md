---
name: orchestrate
description: >-
  Coordinate a fleet of builder agents on parallel work at minimum cost: a thin dispatcher plus a
  light-tier watchdog, not a standing supervisor. File work items with their acceptance criteria,
  spawn builders at the right model tier in isolated worktrees, let the merge queue serialize, and
  drive by events instead of polling. Each builder owns its PR through to merge. Use when several
  independent work items run in parallel and must land without a per-step coordinator; prefer it over
  an ad-hoc watch loop whenever you would otherwise poll PR status.
license: MIT
compatibility: any
metadata:
  version: "1.1.0"
---

# Orchestrate: coordinate a builder fleet cheaply, by events not polling

Coordination state lives in the **tracker** and the **merge queue**, which builders read directly. The
orchestrator assigns, spawns, watches for events, and synthesizes at the end. It does NOT poll PR status
or relay "rebase now": both are the expensive, unreliable path a merge queue plus builder ownership
already covers.

## When this fits, and when not

Fits: several **independent** work items (disjoint write-sets) that run in parallel and must land, where
you would otherwise babysit them. Not: a single item, or sequential work, which one builder (or you)
just does. Parallelism is not free; for a solo operator the token and integration cost often beats the
wall-clock win, so reach for a fleet only when the seam is real (the `graph-engine` skill divides the
work and says the same).

## Tiers: run the cheap work cheap

Tier names map to models in the host config (see the model-tier guidance); the point is the routing, not
the names.

- **Dispatcher, watchdog, and status: Light.** A coordinator that reads large context and emits a few
  tokens per check is light work. Running it on the Reasoning tier is the canonical waste.
- **Builders: Execution.** Pass the Execution model as the spawn override. Do not let a builder inherit
  a Reasoning-tier parent; that silently runs every builder on the most expensive model.
- **A genuinely hard design or spec node: Reasoning**, used sparingly and only for that node.

## Dispatch

1. **File each work item in the tracker with its acceptance criteria in the issue itself**, so a builder
   works from the issue, not from relayed chat. Land shared wire or contract seams FIRST (api-first) so
   the consumers can then proceed independently.
2. **Spawn one builder per item** with the Execution model override and `isolation: "worktree"`, so
   parallel builders never share a checkout. A shared checkout lets one builder's branch switch drop a
   peer's uncommitted work.
3. **Verify shared facts from source before you put them in a brief.** Read the default branch from
   `gh repo view --json defaultBranchRef`, not memory. A wrong fact handed to the whole fleet costs one
   correction per builder.

## Builder brief: what each builder owns

- **Drive your PR to MERGED, not to "enqueued".** Handle your own rebase when it goes BEHIND or DIRTY
  (`gh pr update-branch`), the CI re-runs, and the review replies. Hand back only on MERGED or a real
  blocker you cannot resolve. Work ends at merge, not at push. Watch the PR with a diffing change-request watcher
  that prints only actionable changes (git-workflow's `babysit` when installed), not a poll loop.
- **Queue-only:** enqueue with auto-merge; never admin-bypass a required check.
- **Isolation and hygiene:** your own worktree; stage explicit paths (never `git add -A`); run the
  repo's checks locally and green before pushing.

## Drive by events, not a cron

A wall-clock poll loop is the anti-pattern: it burns Reasoning-context reads for a few output tokens, and
it tracks state worse than the primitives do. Use the harness signals:

- **Builder completion** wakes you through the subagent hand-back. Collect results from the hand-back
  itself, not from files the agent was told to write (agents routinely skip the file).
- **Stall:** a task-notification fires when an agent stops with no live children. Send a short resume
  message once; if it stalls a second time, respawn it fresh rather than nudging again.
- **Idle:** `notify_when_idle` gives a one-shot "it went idle" signal without polling.
- **PR and CI:** each builder runs its PR watcher (`babysit` under `Monitor`, re-armed on expiry);
  `ReadNotifications` delivers GitHub activity on subscribed PRs. Let the merge queue land green, approved PRs on its own.
- Query `mergeStateStatus` plus `statusCheckRollup`, not `mergeQueueEntry` (the latter errors on some
  `gh` versions).

## Synthesize, then stop

When the items land, integrate and report once; isolated contexts do not integrate themselves (the
serial integration pass). The orchestrator's job ends when the work is merged and summarized, not by
continuing to watch an empty queue.

## Anti-patterns, learned the hard way

- A standing Reasoning-tier loop polling PR status: roughly a million cache-read tokens for a handful of
  output tokens. Replace with events on the Light tier.
- Builders sharing one checkout: HEAD switches drop uncommitted work. One worktree each.
- A builder that stops at "pushed" or "enqueued": its PR then goes BEHIND and someone else rebases it.
  Builders own their PR to merge.
- Broadcasting an unverified fact (the default branch, a path, a command) to the fleet: one wrong
  instruction fans out to every builder at once.
