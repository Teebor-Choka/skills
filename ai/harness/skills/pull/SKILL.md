---
name: pull
description: >-
  Work as one peer in a swarm: pull items from a shared work board, claim, hold a lease, hand
  off on the item. Use for "swarm of builders", "report for work duty", "take from the board",
  "load harness:pull, role X". Not for dispatcher-led work.
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# harness:pull: peer-to-peer swarm

Loaded as a plugin, this skill is `harness:pull`. Copied or symlinked as a bare skill
directory, the host knows it only as `pull` and `Skill harness:pull` fails with "Unknown
skill". If it fails, load `pull`.

> **First read [`../../references/mechanics.md`](../../references/mechanics.md).** It defines the claim,
> lease, reap, hand-off, escalation and wind-down rules this mode builds on, and how an agent in a
> run loads its role card (`../../references/roles/`) and skills.

Use when work spawns work: review-fix loops, many agents on one interacting surface, items that
cannot all be known up front. Peers pull items from the board. No dispatcher relays or starts
passes. The mechanics in `mechanics.md` apply unchanged; this file adds what is specific to pull.

## Pull rule

1. Reap stale claims first (`mechanics.md` rule 4).
2. List items whose state is in your role's pull set (charter). Prefer the item whose `area` label
   matches the area you touched last. Affinity is a preference, never a reason to leave an
   item unclaimed.
3. Claim it (rule 2). If you lose the race, pull again.
4. If no item matches, report `waiting for next item` on the board (a note on your last item, or
   the charter's idle marker) and re-check when the board changes. Do not poll on a short timer.

## Blocked: never wait, never ask

1. When you are blocked on a peer or a gate (CI, review, merge queue), release nothing you own.
   Take the next ready item in another worktree.
2. Escalate only through the charter's escalation label. Do not message the owner or a peer.
3. When you are blocked on the owner, post once on the item, stop the loop and resume on a board
   event. Do not schedule a repeated wakeup with the same prompt.
4. When the owner's phrase is ambiguous, confirm the reading once and record it in the charter.
5. **Autonomy comes from the brief.** It states one level: `ask`, `ask-only-destructive` or
   `never-ask-escalate-by-message`. State the grant in the brief; never infer it from an earlier
   session or a peer message. With no level stated, ask. At the third level, escalate by message
   to the escalation channel and block on the human only for a destructive or irreversible step.

## Wake on events

- Do not run a timer tick. Wake on a task notification or a message. For board changes run one
  monitor that prints a line only when the board changes. List running monitors before you start
  one and never start an identical command twice.
- Do not list agents within 5 minutes of the last call, unless a hand-back is overdue.
- Do not end a turn with work pending. End it with an armed monitor, or with a question only the
  owner can answer.
- A worker with no item ends its session. Reschedule an idle wakeup at most twice. Prefer a fresh
  session per item over one that carries days of context.
- Stop a background task by an id from the current task list. An id from before a compaction is
  stale.
- Ask only peers whose repo matches the question, one first. Start every outbound message with
  your session name and role.

## Claims and review

- A push or PR-open for an item must refuse when another assignee or a live lease exists
  (hook or check; the rule holds without it).
- Review is an item. Claim it atomically and hold a lease, so two reviewers never cover the same
  PR. Post `review-lease: <id>` on the PR before you spawn a reviewer.
- A handoff is a comment on the item (branch, worktree, state, next step, do-not-touch) plus a
  `handoff` label. A new session reads the board before it messages any peer: list the items
  with holder and heartbeat age, the open PRs per item, and the stale leases (on GitHub:
  `gh issue list -l handoff`, `gh issue list -l state:in-progress` with the age of each lease
  comment, and `gh pr list`). Act on that list. Ask a peer only when the board is empty.

## State file and handoff

A coordinator session is not a place to live. After 2 compactions or 1,500 turns, write `STATE.md`
(goal, leases, open PRs, next 3 actions) and hand off to a fresh session. Count active hours,
compactions and context size, not session age. Update `STATE.md` at each wake-up, at each
compaction, and at turn end with work pending. A pick-up session reads `STATE.md` first, then
reads the board as above, and does not ask peers.

Do not edit files in a peer's checkout. Edit in your own worktree or hand the edit to the item's
builder. On "File has been modified since read": Read, then re-apply. Never retry the same edit.

## Self-starting passes

Nobody starts a pass for you. When a reviewer's area has no open findings, the reviewer files the
next pass item for that area (rule 6). The charter's clean-pass rule (for example, two clean
passes end an area) and wind-down are flags on the board, not instructions from a dispatcher.

## Who does what

The dispatcher, if one exists, only spawns agents and answers owner escalations. It holds no
state. The steward audits lease health. The curator keeps the board small. Roles and their pull
sets come from the charter.

## What pull costs

Every agent re-reads the board, so keep items short and closed items out of the way (curator).
Pull needs a board binding that supports atomic claim and a visible heartbeat age. Check this in
the binding before the first claim: if two agents read different stores, both claim the same item.
