# Disciplines

The craft behind the loop. These are generic and project-agnostic; the _which_ and _how
strict_ come from `.agents/policy` (`practices`, `gate`), not from here. This is the single
home for them — an `AGENTS.md`/`CLAUDE.md` points here instead of restating.

## Test-first, matched to scope

- **ATDD at the boundary** (`practices.scope: ATDD`). For a module, component, or
  architectural unit, start from acceptance tests derived from the spec, expressed at the
  unit's public contract and agreed before design. They define "done" and frame the inner
  loop.
- **TDD at the unit** (`practices.task: TDD`). Red → green → refactor at the unit boundary.
  The failing test is that slice's spec; write no production code no failing test is asking
  for.
- **Build top-down, fail bottom-up to green.** Acceptance tests set the outer boundary; unit
  tests fill it in.

### The red must be functional

A test that does not compile is not a red. The failing test must **run and fail on
behaviour** — the output is wrong or the function is absent — not fail to build. Commit it
before the implementation; that commit is the artifact the review gate and `policy-gate tdd`
check for. A green that was never preceded by a real red proves nothing.

### Reproduce at the smallest boundary first

Replicate a bug in the smallest testable unit before an integration/slow test. Feed the known
inputs (from logs, a prior run) directly to the unit. A unit test that eliminates a subsystem
beats a slow run that tests one guess. Assert the **bad** behaviour too — a silent no-op is
externally indistinguishable from correct until a test names it.

## Specify before building

A requirement states intent; a specification states behaviour. Before code, the work item must
pin five categories — any blank one is a default no one approved:

- **Valid inputs** — types, ranges, null/empty/absent.
- **Expected output** — the exact "done".
- **Failure** — what counts as failure, then what (retry, fallback, alert, drop).
- **Performance/scale** — volume, latency, concurrency.
- **Dependency behaviour** — what each external call guarantees, and behaviour when it doesn't.

**AI-gap self-test:** "if an agent built this, passed my tests, and still behaved wrong — what
did I miss?" The answer is always a specific unspecified behaviour; add it to the spec now.

Getting a requirement to a spec:

1. **Interrogate first.** List 4–6 behavioural questions the requirement leaves open
   (triggers, definitions, channels, failure retries, volume). Never "which framework". Answer
   them or ask the human, on the item, before any code.
2. **Write behaviourally.** "When [event], the system shall [do Y via Z], provided [condition].
   If [failure] after [N] retries, [fallback]." Label each assumption. A line you cannot write
   an acceptance test from is still a requirement.
3. **Draw the scope boundary.** State what is deliberately excluded and why; implicit scope is
   scope the agent invents.
4. **Close the gap.** Run the AI-gap self-test and add the constraint it finds.

Spec block, at the top of the work item:

```markdown
## Spec: <feature>

Intent: <the one-line requirement>
Valid inputs / Expected outputs / Failure def / Scale / Dependencies: <the five categories>
Assumptions (explicit): <each one labelled>
Out of scope: <excluded, and why>
AI-gap I closed: <the under-spec the self-test surfaced, now constrained>
Acceptance tests (written before the build, at empty / zero / one / max / null / concurrent and every failure path):

- [ ] <case> -> <expected>
```

## Surgical change

Smallest change that satisfies the item. Match surrounding style. Touch only what the item
needs; park unrelated improvements as new work items. Remove only the orphans your change
created, never pre-existing dead code. Every changed line traces to the item.

## Evaluate as a steerer, not a dumper

- Derive acceptance tests from the spec yourself; don't let one agent write both the code and
  the tests that grade it (the echo chamber — both wrong the same way).
- Read output before running it; check against the spec, not "does it compile".
- **Adversarial reading** starts at boundaries and error paths, not line one. Style is what a
  model gets right; hunt behavioural defects — silent empty-return, off-by-one retry, a
  staging/production assumption.
- Fix by adjusting the spec, not re-rolling — a lucky re-roll hides the gap.
- Accountability gate before approving: "would I own this in production, and can I say _why_?"
  Tests I designed against failure paths are the signal, not "tests pass".

## Enforce in architecture

Add the failure-path test the agent did not write, and assert the bad behaviour too. Then make
the invariant survive the next changer, who has no memory of this change:

- **Machine-enforced contracts.** Encode invariants in types and CI, not comments.
- **Domain-language errors.** "notification provider unreachable, queued for retry", not
  `ECONNREFUSED`.
- **Visible surface over hidden substrate.** Legible at the layer the next person works at.

Source: distilled from _The AI-Era Engineering Playbook_ (Gabor Mayer,
https://aieraengineering.com, CC BY 4.0), Product-Engineer Stage-1 (Specification) and Stage-2
(Build & Evaluation) rubrics.

## Defending and deferring in review

- **Defend when right.** A wrong review comment gets a reasoned reply, not a reflexive change.
- **Defer out of scope.** In-scope fixes land in the change; larger or out-of-scope findings
  become new work items, linked. The change does not balloon.
