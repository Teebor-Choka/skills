# Filing the work to the tracker

The package is designed and lint-clean; the architect's last act in Phase A is to **file the work**
to where the policy says it lives, then stop. Dispatch, execution, and integration are other
processes' jobs — the architect does not run them.

## Destination (policy-driven)

Read `work.tracker` from `.agents/policy` via the `policy` skill:

```
policy_loader.py <repo> --get work.tracker
```

The value selects a **binding** (`github`, `gitlab`, `jira`, `beads`, …) that resolves the abstract
verbs — file an item, link a dependency. Adding a tracker is adding a binding, not changing this
skill. Unset: default to `github` when the repo has a GitHub remote and `gh` is available, else
`none` — file nothing to a tracker, and the package directory stands as the deliverable.

## What gets filed

One work item per **spec block** (`full` tier) or the single `<slug>-plan.md` (`note`/`small`) — the
unit an executor (e.g. `implement`) picks up. Each item carries, verbatim from the package:

- the block's objective, interface contract, and both test tables (positive + adversarial);
- its **dependency edges** as an explicit `Blocked by: <item>` / `Blocks: <item>` summary, taken from
  `development-graph.md`, so execution order is unambiguous without reading the whole set;
- a link back to the package (path or commit) so the full context is one hop away.

File in dependency order, so a blocker's id exists before the item that cites it.

## Isolation and the optional coordination channel

The graph step already cut the blocks for **disjoint write-sets** (collision-free waves). Where two
blocks are not cleanly disjoint — they touch a shared boundary the design could not fully separate —
the architect **declares** it: a line in both items naming a shared coordination channel for
execution (e.g. a linked discussion). It is a marker the executor honors; the architect never opens
or runs the channel.

## Terminal

Filing ends **Phase A**. Dispatching the filed items to implementers and integrating their changes
is the executor's job — `implement` plus on-demand subagent dispatch per the graph — including the
mandatory serial integration pass the executor must not skip. The architect does not run that loop.
(Deploying the _designed system_ itself hands-off, when the package will be deployed, is the
architect's separate **Phase B** — `references/execution.md` — not the work-item execution above.)
