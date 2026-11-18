---
name: decompose
description: >-
  Split a goal into parallel work units and file them as board items, each with one write-set,
  dependencies, tests and model tier. Use for "split/divide/parallelise this" or before an
  orchestrate run. Not for a single unit.
license: MIT
compatibility: any
metadata:
  version: "1.1.0"
---

# decompose: cut the work, check the cut, file the units

A cut is good when each unit has one write-set, one deliverable and a check that can fail. Splitting
is not free: isolated contexts need a serial integration pass, and for a solo operator the token
and integration cost often beats the wall-clock gain. Cut only where the seam is real.

## Scope

- **Takes in:** the architect's spec blocks and dependency graph (or any goal with real seams).
- **Files:** non-overlapping units of work as board items. Each item is the per-unit brief for a
  worker. It is not a separate artifact. It carries the unit's objective, interface, positive AND
  adversarial acceptance tests, write-set, dependencies and tier, taken from the spec blocks.
- **Never does:** design the system (use `architect`), write a second brief beside the item, or run
  the units (use `orchestrate:assign` or `orchestrate:pull`).

## Steps

1. **Decide whether to cut.** One unit, or work with no disjoint write-sets, has nothing to divide.
   Stop and do it sequentially. Say so.
2. **Find the seams.** Cut at interfaces: a schema, an API, a file boundary, a document section.
   Land shared contract seams first as their own units, so consumers proceed independently.
3. **Write each unit.**

   | Field       | Content                                                                                           |
   | ----------- | ------------------------------------------------------------------------------------------------- |
   | id          | Stable, unique.                                                                                   |
   | objective   | What the unit achieves, in a short paragraph. Taken from the spec block.                          |
   | interface   | The contract the unit exposes or consumes: inputs, outputs, config surface.                       |
   | deliverable | One thing, nameable in a sentence.                                                                |
   | deps        | Ids it consumes. Only true dependencies.                                                          |
   | write_set   | Every file or resource it mutates. Parallel safety is decided on this.                            |
   | acceptance  | Positive and adversarial tests that can fail. Derived from the spec, not from the implementation. |
   | tier        | `reasoning`, `execution` (default), `light`, or `speed`. Readers and validators are `light`.      |
   | area        | Optional label for pull-mode affinity.                                                            |

4. **Check the cut.** Write the nodes (`id`, `deliverable`, `deps`, `write_set`, optional `cost`
   and `loops`) to a JSON spec and run the engine that ships with the `graph-engine` skill:

       python3 <graph-engine dir>/graph.py spec.json

   It returns waves, the critical path, barriers and the concurrency cap. It exits non-zero on a
   cycle, a dangling dependency or a write-set collision inside a wave. Fix the cut, not the check.
   `graph.py` does not read `tier` or `acceptance`: they stay on the item.

5. **File the units** (destination, contents and coordination channel: `references/filing.md`). Use the board verbs (`references/board.md` of the `orchestrate` plugin; the tracker is the
   charter's `board`, else the policy key `work.tracker`). File in dependency order so a blocker's
   id exists before the item that cites it. Each item is the unit's brief: it carries the objective, interface, acceptance tests, write-set, tier, a
   `blocks`/`blocked-by` summary taken from the graph, and a link back to the spec.
   Mark an item that consumes another unit's output `blocked_by` that item. Never branch one
   unit's work from another unit's branch: the stack re-conflicts on every merge below it.
6. **Pick the mode.** Units known and disjoint, each finishing alone: `assign`. Units that spawn
   follow-on work or review loops: `pull`. Hand the filed board and the choice to `orchestrate:assign` or `orchestrate:pull`.

## Do not

- Start more work on a branch cut before a restructure that is in flight. Rebase onto the
  restructure first.
- Create worktrees outside the one `<repo>-worktrees/` directory the run names (for example
  `sandy-worktrees/`).
- Split units that share a write-set to gain parallelism. Merge them or order them.
- File a unit with no acceptance tests, or tests written only by the unit's implementer.
- Hide a shared boundary. Where two units cannot be cleanly disjoint, say so in both items.
- Run the units. Dispatch and integration belong to `orchestrate:assign` and `orchestrate:pull`.
