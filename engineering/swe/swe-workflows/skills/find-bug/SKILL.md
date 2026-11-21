---
name: find-bug
description: >
  Turn a bug report into a committed failing test at the smallest boundary, after proving a
  contract is violated. Use for a bug, regression or repro. implement then fixes it. Not for
  new features.
metadata:
  version: "0.1.0"
  group: swe-workflows
  siblings: [implement, triage]
---

# find-bug — the reproduction loop

Pin a defect to a **committed functional red** before anyone fixes it. The red is the artifact
the fix is held to: `implement` turns it green, and the isolated adversarial reviewer confirms
it was a real functional failure. find-bug ends where implement begins.

Two cheap mistakes this skill exists to prevent: calling a reproducible behaviour a bug without
proving it breaks a contract, and reaching for a slow integration test when a unit test would
isolate the fault in milliseconds.

Read `../implement/references/disciplines.md` for the test craft, `../implement/references/bindings.md`
for the forge mapping, and the `policy` skill (`harness:policy`, `ai/harness` in this repo) for the loader contract.

## The flow

```
take a bug report, regression, or gotcha
  → establish the contract   name the documented/type/runtime guarantee the behaviour breaks
  → locate the boundary      the smallest unit that could exhibit it; eliminate subsystems first
  → reproduce                feed the exact inputs; a FUNCTIONAL red (runs and fails on behaviour)
  → assert the bad behaviour  a silent no-op must be distinguishable from correct
  → commit the red           that commit is the artifact; hand a spec'd fix item to implement
```

**Gate:** write the red test from the issue before any root-cause analysis or comment. A request
to "go through the issue or PR and establish the facts" is an analysis request: reproduction is
part of the deliverable, so the red still comes first.

Resolve policy once: `../implement/scripts/policy-gate.sh <repo> show`. With `task: TDD` the
committed functional red is mandatory before a fix; it is also what the commit gate and the
reviewer look for.

### 1. Establish the contract

A reproducible error is not automatically a bug. First name the contract the behaviour breaks:
a documented guarantee, a type-level invariant, or an established runtime contract. If nothing
is violated, this is a spec gap, not a defect: route it to `triage`, do not invent a fix.

### 2. Locate the smallest boundary

Find the smallest unit that could exhibit the behaviour. Prefer eliminating subsystems with
fast unit tests over confirming a guess with a slow run: a test that rules a subsystem out is
progress; a slow pass that confirms one hypothesis is a bonus. Before any slow or integration
run, confirm the change is in the component that does the work, and that the component under
test is the build actually carrying it (multi-process and multi-repo setups routinely pin some
participants to a fixed build).

### 3. Reproduce as a functional red

Feed the exact inputs (from logs, instrumentation, or a prior run) to that unit. The red must
be a **functional failure:** it runs and fails because the behaviour is wrong, not because it
fails to compile. Prefer instrumenting a value to inferring it: never conclude a mechanism is
inactive from an absent log line or an empty grep without checking it could have been observed
at all (log level compiled out, wrong target, artefacts deleted on teardown, stale binary).

If you cannot reproduce the bug, report that as the result. Name each level you tried (unit,
integration, smoke or end to end), the exact inputs and environment used, and what blocked a
red at that level. Do not invent a fix, and do not commit a test that passes. An unreplicable
report is a finding: hand it back with the missing facts it needs (logs, versions, data).

### 4. Assert the bad behaviour

Assert the defect, not only the correct path. A silent no-op (a zero limit, a disabled gate, a
default that switches a feature off) is externally indistinguishable from correct behaviour, and
is what makes a bug expensive to find. The test must fail loudly on the actual defect.

### 5. Commit the red, hand off

Commit the failing test: that commit is the artifact `implement`'s commit gate and the
adversarial reviewer check for. Open or update the work item with the reproduction and the
correct behaviour as its acceptance criteria, then hand to `implement` to drive red to green.
If reproduction surfaces a second defect, file it as a linked item; do not widen scope.

## Enforcement

find-bug's deliverable is the committed functional red itself, a git artifact, not a claim. It
is validated externally: the commit boundary's gate (`../implement/scripts/forge-state.sh`, via
the hook) looks for the test-touching commit, and the isolated adversarial reviewer confirms the
red failed on behaviour, not compilation. find-bug adds no new boundary.

## Portability

Forge-neutral and language-neutral: "the smallest unit" and "instrument the input" are intents
each stack realises its own way. The forge is named only in
`../implement/references/bindings.md`. No assumption of a build system or host.

## Group

Part of the swe-workflows group with `triage` (spec a vague item) and `implement` (red to
integrated change).
