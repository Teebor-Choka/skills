# Adversarial review: a fixed dimension catalog

The proposal's validation pass (`principles.md` §4, `document-set.md` proposal item 9) attacks the
design. Left open, that pass reinvents its attack angles every run. This file fixes them: a catalog of
dimensions, a prompt template for fanning the attack out to read-only reviewers, and the rule for
folding findings back in.

## The dimensions

Run every dimension in the table that applies. Drop one only with a written reason ("no state, so
nothing to corrupt"); a silent skip is the gap this catalog exists to close. Each row gives the
question, then how it reads in three kinds of work.

| Dimension                | Question                                                                      | Software                                                        | Infra                                                                        | Non-software (process, policy, program)                                   |
| ------------------------ | ----------------------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Correctness**          | What input or sequence makes the result wrong while everything looks healthy? | lost, duplicated, reordered, or stale data; wrong at a boundary | config drift; a replica that is up but diverged; clock skew                  | a figure counted twice; a rule applied to the wrong population            |
| **Feasibility**          | What does the design assume is possible that has not been shown to be?        | an API, throughput, or latency never measured                   | quota, capacity, license, lead time, a version that lacks the feature        | a headcount, budget, or approval no one has confirmed                     |
| **Operations**           | Who runs this at 3 a.m., and what do they see when it breaks?                 | no metric for the bad state; an alert that cannot fire          | no runbook; a rollout that cannot pause; secrets or certs that expire        | no owner after launch; a handoff that depends on one person               |
| **Coexistence**          | What breaks while old and new run side by side, or when only one half lands?  | mixed versions; schema or protocol skew; dual-write races       | partial rollout; two control planes; a migration that cannot be paused       | two procedures in force at once; staff trained on the old one             |
| **Failure and recovery** | What is the worst partial failure, and what undoes it?                        | a crash between two writes; a retry that repeats a side effect  | a zone or dependency loss; restore never tested; a backup that is unreadable | a key person leaves mid-rollout; the pilot fails and there is no way back |
| **Security and trust**   | Who or what can abuse this, and what does it trust without checking?          | injection; an unvalidated input; a token scoped too wide        | a network path or role broader than needed; a shared credential              | a role that can both approve and execute; an unaudited exception path     |
| **Scale and cost**       | What grows faster than the design assumes, and what does it cost at 10x?      | an unbounded queue, scan, or fan-out                            | egress, storage, or licence cost at volume; a limit hit under load           | cost per case rises with volume; a manual step that stops scaling         |
| **Evidence**             | Which load-bearing claim rests on recall or a single source, not a check?     | a library behaviour cited from memory                           | a vendor limit cited from a stale page                                       | a statistic or precedent never traced to its source                       |

Add a dimension the domain demands (regulatory, safety, accessibility, data residency). Do not remove
the eight above to make room.

## Fan-out to read-only reviewers

One reviewer per dimension, run in parallel, each seeing the same package but attacking one angle.
Reviewers are read-only: they report, they never edit the proposal. A reviewer that also fixes the
design stops being adversarial.

Prompt template (one instance per dimension; fill the brackets):

```text
You are an adversarial reviewer. Your single angle is [DIMENSION]: [its question from the catalog].
Read-only: do not edit any file.

Read: [paths to research-notes.md, the proposal, decision-log.md, and the spec if it exists].
Domain: [software | infra | non-software], so read the [matching column] of the catalog row.

Task: try to break the design on [DIMENSION]. Find the concrete scenario, not a general worry.
Ground each finding: cite the proposal section or decision id it attacks, and the evidence (a repo
path, a doc URL, a measured figure). If you cannot ground it, mark it UNVERIFIED instead of dropping it.

Return a table, one row per finding:
| id | dimension | scenario (input/sequence/event) | what breaks | severity (blocker/major/minor) | attacks (section or decision id) | evidence | suggested fix or test |

If you find nothing, say what you tried and why it held. An empty report with no attempts listed is a
failed review.
```

Fan-in: one synthesizer merges the tables, de-duplicates findings that two reviewers reached by
different routes, and keeps the higher severity. Handle partial results explicitly: a reviewer that
errored or timed out is listed as "not run", never read as "found nothing".

## Folding findings back in

- **Blocker or major, design changes:** edit the proposal so the design answers it, record the change
  as a decision in `decision-log.md` (Decision, Why, Grounding; cite the finding id), and list the
  superseded option under "considered and set aside".
- **Real but accepted:** keep it as a named risk in the proposal's risks section, or an open item with
  an owner and a gate. Say who accepted it.
- **UNVERIFIED:** an open item with the check that would settle it; do not design around a guess.
- **Dismissed:** a row in "considered and set aside" with the reason, so the next review does not
  raise it again.
- **Every kept finding that can be tested** becomes an adversarial test row in the affected spec block
  (`methodology.md`: the bad behaviour must be observable), carrying the finding id.
- **Validation pass output:** the proposal's section 9 lists the findings by dimension with their
  disposition (changed, accepted, unverified, dismissed). A pass where every dimension reports
  "nothing" did not run (`principles.md` §4); go back and read the reviewers' attempt lists.
- **Scale to the tier.** `note`: run the catalog yourself as a checklist, one line per dimension, no
  fan-out. `small`: fan out only the dimensions that carry the hinge decision. `full`: all dimensions.
