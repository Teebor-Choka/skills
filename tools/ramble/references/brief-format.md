# Brief format — the ramble → architect handoff

Emit exactly this when the frontier is empty and the user has confirmed shared understanding. The
architect consumes it as the input to grounding and the proposal. It states **scope, not
implementation**: no tasks, no file paths, no acceptance tests — those are the architect's job.

## Structure

```md
# Brief: {title}

## Problem

{One paragraph: what is wrong or wanted, and why it matters now. No solution yet.}

## Intent

- {a thing the result must do or be} — _trace:_ {the thing the user said or that was grounded that this rests on}
- {…}

## Open items

- {a gap that stayed open} — _closes when:_ {who or what resolves it}
- {…}

## Captured (optional)

- Terms settled → `GLOSSARY.md`
```

(Decisions are not captured by the ramble; a decision worth keeping is the architect's to record in its
decision-log. Unresolved decisions appear above as open items.)

## Rules

- **Every intent bullet carries a trace.** If it wasn't said in the interview or grounded by a
  sub-agent, it is not intent — it is an open item, or it is cut. No invented requirements.
- **Open items are explicit, never silent assumptions.** Each names who or what would close it. A gap
  you could not resolve in the interview lands here, not as a quiet default.
- **Scope, not implementation.** The brief is the _what_ and _why_ at the altitude the architect needs
  to start; it never carries the _how_.
- **Short.** One page. It is a handoff, not a spec; the architect expands it.

## Worked example

```md
# Brief: weekly status roll-up

## Problem

The weekly status update is assembled by hand from four tools every Friday; it takes ~90 minutes,
is error-prone, and the author is a bottleneck when they are away.

## Intent

- Pull status from the four existing sources automatically — _trace:_ "it's Jira, the deploy log, the
  support queue, and the finance sheet."
- Produce a draft a human edits, not an auto-sent report — _trace:_ "I never want it to send without me reading it."
- Run unattended on a schedule, re-runnable on demand — _trace:_ "Friday morning, but I re-run it if numbers change."

## Open items

- Which of the four sources is authoritative when two disagree — _closes when:_ the user checks with finance.
- Whether last week's draft should seed this week's — _closes when:_ decided after the first real run.
```
