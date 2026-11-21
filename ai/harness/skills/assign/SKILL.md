---
name: assign
description: >-
  Dispatch known, independent units to workers on the right model tier, driven by events not
  polling. Use only when told "load harness:assign, role X". Not for work that spawns work
  (harness:pull).
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# harness:assign: thin dispatcher

Loaded as a plugin, this skill is `harness:assign`. Copied or symlinked as a bare skill
directory, it is `assign`. If `Skill harness:assign` fails with "Unknown skill", load `assign`.

> **First read [`../../references/mechanics.md`](../../references/mechanics.md).** It defines the claim,
> lease, reap, hand-off, escalation and wind-down rules this mode builds on, and how an agent in a
> run loads its role card (`../../references/roles/`) and skills.

Use when the units are known up front, their write-sets are disjoint (cut them with `decompose`),
and each unit finishes on its own. A dispatcher hands units to workers and watches events. It is
thin: it holds no state that the board lacks. The mechanics in `mechanics.md` apply unchanged; this file
adds what is specific to assign.

## Dispatcher

1. **Put each unit on the board with its acceptance tests in the item itself**, so a worker acts
   from the item and not from relayed chat. Land shared contract seams first, so consumers can
   then proceed independently.
2. **Spawn one worker per unit** at the Execution tier (see [cost-isolation-integration.md](../../references/cost-isolation-integration.md)) in its
   own workspace. Claim the item for that worker's id (`mechanics.md` rule 1).
3. **Verify shared facts from source before you put them in a brief** (the default branch, a path,
   a command). A wrong fact handed to the whole fleet costs one correction per worker.
4. **Put the spawn-brief line from the charter in every brief.**
5. **Brief roles and authority as `mechanics.md` says** (one structured message, merge authority
   explicit, delegated decisions). State the grant in the brief; never infer it. Give the human
   the worker's first prompt to paste, or write it to a file the worker reads, with fixed lines:
   repo and path, your session name, merge authority (`human only` or `coordinator may arm
auto-merge`), report channel, stop rule. The worker must not need a later peer message to learn
   its role.
6. **Start every brief with a worker preamble:** the worktree path to use (paths under it only),
   which search tool exists on the host (for example `rg` may be absent), the code-graph project
   name or `unavailable`, and "one plain git command per shell call". Index the worktree or tell
   the worker to use the main checkout path. Add: the base branch, the branch-name format, the
   repo's dev-shell command (do not rely on direnv), "return findings as text", "no foreground
   sleep", the PR workflow skill from policy, and "report once, then stop". Cap parallel workers
   per wave. Verify each PR with one script, not by re-reading reports.
7. **Do not fork a babysitter or poller.** Fork only when the child needs the full conversation.
   Otherwise spawn a fresh worker on the Execution tier with a self-contained brief. A fork
   inherits the parent's model and is not a cheap path.

The dispatcher runs on the Light tier. A coordinator that reads large context and emits a few
tokens per check is light work. It only dispatches, watches and merges: it runs no builds and
edits no product code, and it never edits files in a worker's checkout. It hands a reviewer a PR
number and does not read the diff itself.

## Worker

- Own the unit until it passes its gate and is integrated. Work ends at integration, not at
  "submitted". For code, the repo's PR workflow (named in policy) defines what that means (own PR through merge, rebase,
  watcher).
- Heartbeat while you work (rule 3). Write the result to the item (rule 5).
- Return contract: the final message carries verified evidence (the gate you ran and its result)
  and the artifact link (for example the PR URL).
- A builder ends at "PR open, local gate green, evidence on the item". A watcher event wakes the
  dispatcher, which spawns a fresh short fixer per "checks failed" or review-thread event. Do not
  keep a builder alive through CI and review waits.
- A worker with no assigned item ends its session. Resume it on demand by message, or spawn a
  fresh one per item. An idle worker reschedules a wakeup at most twice.
- Give a reviewer or gauntlet agent a turn budget and stop it at 2x.
- Start every outbound message with your session name and role.
- Review tier: use the top tier only for security, unsafe, auth or secrets changes, or a diff over
  about 400 changed lines. Otherwise use the Execution tier. A re-review after rework covers only
  the delta.

## Drive by events, not a clock

A wall-clock poll loop reads large context for few output tokens and tracks state worse than the
primitives do.

- **Worker completion** wakes the dispatcher through the host's hand-back. Collect the result from
  the item, not from files the worker was told to write. Agents routinely skip the file.
- **Stall:** the lease is the signal. A silent worker is reaped (rule 4) and respawned fresh. Do not
  nudge a stalled worker: a nudge costs a turn and rarely helps.
- **Idle:** use the host's one-shot idle signal where it exists, not a poll.
- **No timer tick.** Wake on a worker hand-back or a message. For board changes run one monitor
  that prints a line only when the board changes. List running monitors before you start one and
  never start an identical command twice. Do not list agents on a tick.
- **Stop a background task** by an id from the current task list. An id from before a compaction
  is stale.
- **Turn end.** Do not end a turn with work pending. End it with an armed monitor, or with a
  question only the owner can answer.
- **"File has been modified since read":** another writer touched the checkout. Read the file,
  then re-apply the edit. Never retry the same edit.

## Synthesize, then stop

When the units are integrated, run the serial integration pass ([cost-isolation-integration.md](../../references/cost-isolation-integration.md)),
report once, and stop. Isolated contexts do not integrate themselves. The dispatcher's job ends
when the work is integrated and summarized, not by watching an empty board.
