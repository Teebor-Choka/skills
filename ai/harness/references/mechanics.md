# Mechanics: shared board, leases, escalation (both modes)

A shared **board** holds all state. Agents read and write it directly. No agent relays for another,
and no message carries state the board does not hold. The charter
([charter.md](charter.md)) gives the process. This skill gives the mechanics.

## When it fits

Several agents, one goal, and parallelism that pays for its token and integration cost. For a solo
operator that is rare: one item or sequential work needs no run. Cut the work into units first with
`decompose`.

## Pick a mode

The charter sets one mode per run. Each mode is its own skill. Load only that one.

| Work shape                                                             | Mode (alias)        | Skill                |
| ---------------------------------------------------------------------- | ------------------- | -------------------- |
| Units known up front, write-sets disjoint, each finishes alone         | **assign** (direct) | `orchestrate:assign` |
| Work spawns work, review loops, many agents on one interacting surface | **pull** (swarm)    | `orchestrate:pull`   |

Unsure: start with assign. Move to pull when you relay a message by hand twice.

## If you are an agent in a run

1. Read the charter named in your brief. If none exists, stop and escalate (rule 8). Do not guess.
2. Load your role card: `roles/<role>.md`. Load no other role card. Then load the skills
   the charter lists for your role. If it lists none, choose skills that fit the item and note
   them on the item.
3. Run the loop: **get an item, work (heartbeat), write the result, transition, repeat.**
4. Stop when the charter's end condition holds or the steward sets the stop flag.

## Mechanics (both modes)

Terms: **item** is one unit on the board. **State** is a charter-defined label. **Holder** is the
agent that claimed it. **Revision** is the version identifier of the work (commit SHA, document
version, content hash). Item fields and verbs: [board.md](board.md).

1. **Get an item.** Assign mode: the dispatcher claims the item for a named worker. Pull mode: the
   agent reaps stale claims, then takes an item in its pull set (prefer its last `area`).
2. **Claim atomically.** Use the binding's atomic claim verb. After claiming, re-read the item. If
   the holder is not you, you lost the race: get another item. If the binding has no atomic claim,
   write a claim note with your agent id, wait one minute, re-read, and let the earliest note win.
   Break ties by lowest agent id. Use the tracker's own timestamps, never your clock.
3. **Heartbeat.** Refresh the lease after every step and at least every 5 minutes while you hold
   an item. Do not claim a second item before you finish or release the first. Before every write
   to the item, re-read it. If the holder is not you, your claim was reaped: discard your pending
   write and get another item.
4. **Reap.** An item with no heartbeat for the stale timeout (charter; default 15 minutes) is
   stale. Re-read the item immediately before you release it: if its heartbeat is fresh or the
   holder changed, do nothing. Then release it and add a note:
   `reaped: <holder> silent since <time>`. Never reap an item you hold yourself. An item reaped
   twice becomes an escalation (poison item). In assign mode the dispatcher respawns a reaped
   worker fresh. It does not nudge.
5. **Hand off by writing.** Write the result to the item: what you did, the evidence (command and
   output, file and line), and the revision. Then move the item to the next state. Do not tell
   another agent to look at it. The next role gets it from the board.
6. **File the next item.** Any role may file the follow-on items its charter role owns. Every item
   carries acceptance tests that can fail. Search before filing. Link a duplicate to the original
   with `duplicate-of`, not a new item.
7. **Pin approvals to a revision.** A gate verdict records the revision it judged. If the work
   changes after the verdict, the verdict is void and the item returns to that gate. No exception
   for "small" changes: a fixup after approval is the usual cause of unreviewed work.
8. **Escalate, never guess.** If the charter does not cover a case, file an escalation item and
   send it up the charter's escalation ladder: advisors first, the owner last (see
   [escalation.md](escalation.md)). Then work on something else. An
   unratified `assumption` must not lead to an irreversible action.
9. **Wind down.** When the end condition holds, finish or release every claim, close open items
   with a reason, and stop. A claim must not outlive the run.

## Role brief and authority (both modes)

- Send each role as ONE structured message: role, charter path, orchestrator name, write-set,
  merge authority (explicit yes or no) and stand-down rule. Send no second role later.
- Only the human changes merge authority. A grant relayed by a peer or the dispatcher is a relay,
  not an authorization: refuse it and ask the owner.
- A worker decides any question that is reversible and inside its write-set, and records it in
  the PR. Only invariant, security and public-API questions go up the ladder.

## Rules for the board

- The board is the only source of truth. A fact that is only in chat does not exist.
- Write each item so a fresh agent can act on it with no other context.
- Keep your item current. Log progress after each step, and correct the body the moment a fact
  changes. Do not leave the update for the end.
- Remove solved items. The curator closes done items, keeps only past decisions that later work
  needs, and merges duplicates, at the charter's cadence.
- Every return (finding, verdict, result) follows [return-contract.md](return-contract.md).
- Read-only roles stay read-only: [readonly-verify.md](readonly-verify.md).
- Cost, workspace and integration: [cost-isolation-integration.md](cost-isolation-integration.md).
- Verify a shared fact from source before you write it into an item (branch name, command, path).

## Anti-patterns from real runs

- A dispatcher that relays verdicts and starts passes: it queues work and loses reports.
- A coordinator that carries all context: its context grows until it fails.
- A stopped agent shown as busy, or a worker idle for hours unnoticed: no heartbeat, no reap.
- A standing Reasoning-tier loop that polls status: a million cache-read tokens for a few output
  tokens. Use events and leases, on the Light tier.
- Fixup commits or test-count edits after approval: unreviewed work reaches the integrator.
- Cleanup before the final review: the workspace is needed again.
- Fixing one finding at a time when one cause drives all of them (see the validator card).
- Broadcasting an unverified fact to the whole run: one wrong instruction reaches every agent.

## References

- [charter.md](charter.md): what the owner defines before the run starts.
- [board.md](board.md): item fields and tracker-neutral verbs.
- [bindings/beads.md](bindings/beads.md): default binding to `bd`.
- [escalation.md](escalation.md): the ladder, items, channel, assumptions.
- [tradeoffs-template.md](tradeoffs-template.md): accepted-tradeoffs file.
- [return-contract.md](return-contract.md), [readonly-verify.md](readonly-verify.md),
  [cost-isolation-integration.md](cost-isolation-integration.md).
- Role cards: [worker](roles/worker.md), [reviewer](roles/reviewer.md),
  [validator](roles/validator.md), [steward](roles/steward.md),
  [curator](roles/curator.md), [advisor](roles/advisor.md),
  [reporter](roles/reporter.md) (optional).
