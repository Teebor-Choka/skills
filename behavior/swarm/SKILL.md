---
name: swarm
description: >-
  Peer-to-peer mechanics for a swarm of agents that work on one shared goal through a shared work
  board instead of a dispatcher: pull work, claim it atomically, hold it on a heartbeat lease, reap
  silent claims, hand off by writing to the item, pin approvals to a revision, and escalate
  anything unspecified to the owner. Process (roles, states, gates) is NOT in this skill: an
  owner-approved charter defines it. Load it whenever you are an agent in a multi-agent run that
  names a charter and a board ("load skill swarm, role X"), or when you are asked to set up such a
  run. Works for code and non-code work. Not for a few independent items with no shared surface
  (use orchestrate) and not for dividing a spec into blocks (use graph-engine).
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# swarm: how peer agents coordinate without a hub

A shared **board** holds all state. Agents read and write it directly. No agent relays for another,
and no message carries state that the board does not hold. The skill gives mechanics only. The
**charter** (see [references/charter.md](references/charter.md)) gives process.

## Which skill

- A few independent items, disjoint write-sets, one builder each: `orchestrate`.
- Many agents on one interacting surface, work that spawns more work, review loops: `swarm`.
- Start with `orchestrate` if unsure. Move to `swarm` when you relay a message by hand twice.

## If you are an agent in a swarm

1. Read the charter named in your brief. If none exists, stop and escalate (rule 8). Do not guess.
2. Load your role card: `references/roles/<role>.md`. Load no other role card. Then load the skills
   the charter lists for your role. If it lists none, choose skills that fit the item and note
   them on the item.
3. Run the loop: **pull, claim, work (heartbeat), write result, transition, repeat.**
4. Stop when the charter's end condition holds or the steward sets the stop flag.

## Mechanics

Terms: **item** is one unit on the board. **State** is a charter-defined label on the item.
**Holder** is the agent that claimed it. **Revision** is the version identifier of the work
(commit SHA, document version, content hash).

1. **Pull.** Read the board. Reap stale claims first (rule 4). Take an item whose state is in your
   role's pull set. Prefer the item whose `area` label matches the area you touched last.
2. **Claim atomically.** Use the binding's atomic claim verb. After claiming, re-read the item. If
   the holder is not you, you lost the race: pull again. If the binding has no atomic claim, write
   a claim note with your agent id and time, wait one minute, re-read, and let the earliest note
   win. Break ties by lowest agent id. Use the tracker's own timestamps, never your clock.
3. **Heartbeat.** Refresh the lease after every step and at least every 5 minutes while you hold
   an item. Do not claim a second item before you finish or release the first. Before every write
   to the item, re-read it. If the holder is not you, your claim was reaped: discard your pending
   write, and pull again.
4. **Reap.** An item with no heartbeat for the stale timeout (charter; default 15 minutes) is
   stale. Re-read the item immediately before you release it: if its heartbeat is fresh or the
   holder changed, do nothing. Then release it and add a note:
   `reaped: <holder> silent since <time>`. Never reap an item you hold yourself. An item reaped
   twice becomes an escalation (poison item).
5. **Hand off by writing.** Write the result to the item: what you did, the evidence (command and
   output, file and line), and the revision. Then move the item to the next state. Do not tell
   another agent to look at it. The next role pulls it.
6. **File the next item.** Any role may file the follow-on items its charter role owns. Every
   item carries acceptance tests that can fail. Search before filing. Link a duplicate to the
   original with a `duplicate-of` link, not a new item.
7. **Pin approvals to a revision.** A gate verdict records the revision it judged. If the work
   changes after the verdict, the verdict is void and the item returns to that gate. No exception
   for "small" changes: a fixup after approval is the usual cause of unreviewed work.
8. **Escalate, never guess.** If the charter does not cover a case, file an escalation item and
   send it up the charter's escalation ladder: advisors first, the owner last (see
   [references/escalation.md](references/escalation.md)). Then work on something else. An
   unratified `assumption` must not lead to an irreversible action.
9. **Wind down.** When the end condition holds, finish or release every claim, close open items
   with a reason, and stop. A claim must not outlive the swarm.

## Rules for the board

- The board is the only source of truth. A fact that is only in chat does not exist.
- Write each item so a fresh agent can act on it with no other context.
- Keep your item current. Log progress after each step, and correct the body the moment a fact
  changes. Do not leave the update for the end.
- Remove solved items. The curator closes done items, keeps only past decisions that later work
  needs, and merges duplicates, at the charter's cadence.
- State a verdict with evidence. A finding without a concrete failure scenario is rejected.
- Reviewers and validators are read-only on the work. They write to the board only.
- Verify a shared fact from source before you write it into an item (branch name, command, path).

## Anti-patterns from real runs

- A dispatcher that relays verdicts and starts passes: it queues work and loses reports.
- A coordinator that carries all context: its context grows until it fails.
- A stopped agent shown as busy, or a dev idle for hours unnoticed: no heartbeat, no reap.
- Test-count or fixup commits after approval: unreviewed work reaches the integrator.
- Cleanup before the final review: the worktree is needed again.
- Fixing the same area one finding at a time when one cause drives all of them (see the validator
  card for the merge rule).

## References

- [references/charter.md](references/charter.md): what the owner must define before the swarm starts.
- [references/board-contract.md](references/board-contract.md): item fields and tracker-neutral verbs.
- [references/beads.md](references/beads.md): default binding to `bd`.
- [references/escalation.md](references/escalation.md): escalation items, channel, assumptions.
- [references/tradeoffs-template.md](references/tradeoffs-template.md): accepted-tradeoffs file.
- Role cards: [worker](references/roles/worker.md), [reviewer](references/roles/reviewer.md),
  [validator](references/roles/validator.md), [steward](references/roles/steward.md),
  [curator](references/roles/curator.md), [advisor](references/roles/advisor.md),
  [reporter](references/roles/reporter.md) (optional).
