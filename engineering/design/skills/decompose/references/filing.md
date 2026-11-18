# Filing the work to the tracker

The cut is checked by the graph engine; the last act of `decompose` is to **file the work** to where
the policy says it lives, then hand off. Dispatch, execution and integration belong to `orchestrate`
and `implement`, not to this skill.

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

One work item per unit (an architect spec block for the `full` tier, or the single `<slug>-plan.md`
for `note`/`small`), the item an executor such as `implement` picks up. Each item carries, verbatim from the package:

- the block's objective, interface contract, and both test tables (positive + adversarial);
- its **dependency edges** as an explicit `Blocked by: <item>` / `Blocks: <item>` summary, taken from
  `development-graph.md`, so execution order is unambiguous without reading the whole set;
- a link back to the package (path or commit) so the full context is one hop away.

File in dependency order, so a blocker's id exists before the item that cites it.

## Isolation and the optional coordination channel

The graph step already cut the units for **disjoint write-sets** (collision-free waves). Where two
units are not cleanly disjoint, because they touch a shared boundary the cut could not separate,
`decompose` **declares** it: a line in both items naming a shared coordination channel for
execution (e.g. a linked discussion). It is a marker the executor honors; `decompose` never opens
or runs the channel. The architect's spec lint (E10) already rejects a shared write-set that has
neither a dependency edge nor the same `Coordination channel:` line in both blocks.

## Terminal

Filing ends the decomposition. Dispatching the filed items to implementers and integrating their
changes is the executor's job (`orchestrate:assign`, `orchestrate:pull`, `implement`), including the
mandatory serial integration pass the executor must not skip.
