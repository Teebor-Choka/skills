---
name: triage
description: >
  Turn a vague or oversized issue, raw idea, or ticket with blank acceptance criteria into
  implementable items with a spec; output is a work item, not code. Use before implement.
  Not for items that already have acceptance criteria.
metadata:
  version: "0.1.0"
  group: swe-workflows
  siblings: [implement, find-bug]
---

# triage — the spec-hole dispatcher

Make a work item implementable before anyone writes code. An item that reaches `implement`
under-specified becomes a default no one approved: unspecified resolves to the most literal
plausible reading, which is rarely what was meant. triage closes that gap or routes it to
whoever can.

triage produces a **specification, not an implementation.** Its done-criterion is exactly
`implement`'s spec gate: the item carries acceptance criteria an agent could be held to. It
adds no new enforcement boundary; it feeds the one `implement` already has.

Read `../implement/references/disciplines.md` for the spec craft (the five categories, the
AI-gap self-test), `../implement/references/bindings.md` for the forge mapping, and the
`policy` skill (`harness:policy`, `ai/harness` in this repo) for the loader contract.

## The flow

```
take a raw or under-specified item
  → classify         spec gap, design gap, or intent gap?
  → specify          fill the five categories; write behaviourally; label every assumption
  → AI-gap self-test "built, tests pass, still wrong — what did I miss?" → add that constraint
  → size             one deliverable per item; split an oversized item into linked items
  → route            resolve locally, else escalate: design resolver (design) / stakeholder (intent)
  → hand back        a work item that passes implement's spec gate
```

Resolve policy once: `../implement/scripts/policy-gate.sh <repo> show` prints `practices`,
`gate`, `mode`. `practices` sets how the acceptance criteria must be expressible (with
`scope: ATDD`, as acceptance tests at the unit's public contract). `mode: team` means the
item must be claimable and owned in the tracker, not just in a session.

### 1. Classify the gap

Three kinds, three resolvers. Name which one you have before spending effort on the wrong fix:

- **Spec gap** (what exactly should it do): triage resolves it here, by specifying.
- **Design gap** (how it should be structured, a non-trivial architecture choice with
  trade-offs): route to the design resolver (policy key `design`), which produces the work package; triage folds
  its spec blocks back into items.
- **Intent gap** (what the requester actually wants, the priority, what counts as acceptable):
  only the stakeholder can answer. Ask through the project's channel. Do not guess intent.

### 2. Specify the five categories

Fill valid inputs; expected outputs and the exact "done"; failure definition and what follows
(retry, fallback, alert, drop); performance and scale; dependency behaviour and what happens
when a dependency breaks its assumed guarantee. Write behaviourally: "When [event], the system
shall [do Y via Z], provided [condition]. If [failure] after [N] retries, [fallback]." Label
every assumption and state what is out of scope and why. A blank category is a default no one
approved.

### 3. AI-gap self-test

Ask: "if an agent built this, passed all the tests, but behaved wrong, what did I miss?" The
answer is always a specific unspecified behaviour: an undefined "delivered", a missing
idempotency, an unhandled empty result. Add that constraint now. This is the highest-leverage
step, and the one most often skipped.

### 4. Size

One deliverable, one change request per item. Split an oversized or multi-deliverable item
into linked items, ordered by dependency, so each can be taken to a change request on its own.
Do not manufacture items the work does not have.

### 5. Route and hand back

Resolve locally where you can. Escalate a design gap to the design resolver and an intent gap to the
stakeholder: the item stays open and linked to the escalation, never silently guessed. The
output is one or more work items that pass implement's spec gate. From there `implement` takes
a feature item, or `find-bug` takes a defect report.

## Enforcement

triage grades itself against the same external check `implement` uses:
`../implement/scripts/policy-gate.sh <repo> gate spec [--target FILE]` must pass, meaning the
item carries acceptance criteria. triage adds no boundary hook of its own; the spec it writes
is validated downstream by implement's spec gate and by the adversarial reviewer, who reads
the acceptance criteria before the diff.

## Portability

Forge-neutral and tool-neutral. "Route to the design resolver" and "ask the stakeholder" are intents;
the adapter wires the mechanism (a subagent, a tracker comment, a human ping). The forge is
named only in `../implement/references/bindings.md`. No assumption of any build system or host.

## Group

Part of the swe-workflows group with `implement` (spec'd item to integrated change) and
`find-bug` (defect to red test plus spec'd fix).
