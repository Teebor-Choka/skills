# Escalation

An escalation is a board item that asks for a decision. It climbs a **ladder** the charter
defines: zero or more **advisor** rungs (specialists, often on a stronger model tier, each owning
an area), then the **owner**. The charter must name the owner's **channel** (where the owner sees
it) and **answer path** (where the owner replies). A charter with no owner channel is invalid.

## The ladder

1. The asking agent files the item and takes other work.
2. An advisor in the matching rung answers with a confidence: `sure`, or `unsure: <why>`.
3. `sure` ends the escalation. The advisor logs the decision, names its role, and marks it
   `advisor-ruled`.
4. `unsure` forwards the item, with the analysis attached, to the next rung. The last rung is the
   owner.

**Owner-only, whatever an advisor thinks:** irreversible actions (the charter's list), ratifying an
`assumption`, pause or wind-down, and a conflict between two ratified tradeoffs.

An `advisor-ruled` decision may guide agents at once. It enters the tradeoffs file as
`status: advisor-ruled`. The owner ratifies it or overturns it later. Validators weigh a ruled entry
below a ratified one.

## When to escalate

Escalate to the first rung that fits. Reach the owner only through the ladder, or when the case is
owner-only.

- The charter does not cover the case.
- Two accepted tradeoffs conflict, or a finding contradicts one.
- A poison item: reaped twice, or two fix rounds that did not converge.
- A decision is irreversible (see the charter's list).
- Pause, stop, or wind-down needs the owner.
- An `assumption` from an unattended charter needs ratification.

## Item format

```
type: escalation
asks: <the decision, one sentence>
options: <A, B, C, each with the cost>
recommendation: <one option and why>
default-if-silent: <a safe, reversible action; or "wait">
blocks: <item ids that cannot proceed>
```

Rules:

1. The default-if-silent is never irreversible. If no safe default exists, the default is "wait".
2. After filing, take other work. Do not poll in a loop: re-read the item when you next pull.
3. The owner answers by writing a note on the item. The answerer's note is the decision.
4. The agent that filed it, or the steward, copies each decision that sets a rule into the
   tradeoffs file with its status, then the curator closes the item.

## Channels

The charter picks one or more. Examples: the terminal session of the dispatcher, a push
notification, a tracker comment, a chat message. A channel that posts outside the team is an
outward-facing action: the owner approves it once in the charter.

Escalation volume is a signal. If one area keeps producing escalations, the steward files a
single design escalation for that area instead of many small ones.
