---
name: assign
description: >-
  Run a thin-dispatcher fleet (alias: direct): a dispatcher files known units on a shared work
  board, claims each for a named worker, spawns workers at the right model tier in their own
  workspace, and drives by events and leases instead of polling or relaying. Use when the units are
  known up front, their write-sets are disjoint and each finishes alone, or when you are told "load
  orchestrate:assign, role X". Process (roles, states, gates) comes from an owner-approved charter.
  Works for code and non-code work. Not for work that spawns work or peer review loops (use
  orchestrate:pull), not for cutting work into units (use decompose), not for git and PR mechanics
  (use git-workflow), and not for one item (just do it).
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# orchestrate:assign: thin dispatcher

Loaded as a plugin, this skill is `orchestrate:assign`. Copied or symlinked as a bare skill
directory, it is `assign`. If `Skill orchestrate:assign` fails with "Unknown skill", load `assign`.

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
   explicit, delegated decisions).

The dispatcher runs on the Light tier. A coordinator that reads large context and emits a few
tokens per check is light work.

## Worker

- Own the unit until it passes its gate and is integrated. Work ends at integration, not at
  "submitted". For code, `git-workflow` defines what that means (own PR through merge, rebase,
  watcher).
- Heartbeat while you work (rule 3). Write the result to the item (rule 5).

## Drive by events, not a clock

A wall-clock poll loop reads large context for few output tokens and tracks state worse than the
primitives do.

- **Worker completion** wakes the dispatcher through the host's hand-back. Collect the result from
  the item, not from files the worker was told to write. Agents routinely skip the file.
- **Stall:** the lease is the signal. A silent worker is reaped (rule 4) and respawned fresh. Do not
  nudge a stalled worker: a nudge costs a turn and rarely helps.
- **Idle:** use the host's one-shot idle signal where it exists, not a poll.

## Synthesize, then stop

When the units are integrated, run the serial integration pass ([cost-isolation-integration.md](../../references/cost-isolation-integration.md)),
report once, and stop. Isolated contexts do not integrate themselves. The dispatcher's job ends
when the work is integrated and summarized, not by watching an empty board.
