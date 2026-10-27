# Escalation

An escalation is a board item that asks the owner for a decision. The charter must name the
**channel** (where the owner sees it) and the **answer path** (where the owner replies). A charter
with no channel is invalid.

## When to escalate

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
4. The agent that filed it, or the supervisor, copies each decision that sets a rule into the
   tradeoffs file, then closes the item.

## Channels

The charter picks one or more. Examples: the terminal session of the dispatcher, a push
notification, a tracker comment, a chat message. A channel that posts outside the team is an
outward-facing action: the owner approves it once in the charter.

Escalation volume is a signal. If one area keeps producing escalations, the supervisor files a
single design escalation for that area instead of many small ones.
