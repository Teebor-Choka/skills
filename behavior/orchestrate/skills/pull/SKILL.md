---
name: pull
description: >-
  Run a peer-to-peer swarm (alias: swarm): agents pull items from a shared work board, claim them
  atomically, hold them on a heartbeat lease, hand off by writing to the item, and escalate up a
  ladder that ends at the owner. No dispatcher relays or starts passes. Use when work spawns work
  (review-fix loops, many agents on one interacting surface, items not all known up front), when a
  run needs peers to cooperate without a hub, or when you are told "load orchestrate:pull, role X".
  Process (roles, states, gates) comes from an owner-approved charter. Works for code and non-code
  work. Not for known, disjoint units handed out by a dispatcher (use orchestrate:assign), not for
  cutting work into units (use decompose), and not for one item (just do it).
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# orchestrate:pull: peer-to-peer swarm

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
