# Angle briefs

One brief per reviewer. Paste the shared header, then exactly one angle. Every angle ends with the
same line: **This angle only; do not report anything outside it. Report only; do not edit any file.**

## Shared header

> You are reviewing one block of a larger change. Inputs: the block spec (path), the diff
> (`git diff <base>...HEAD -- <write-set>`), and read access to the repo. Judge the diff against the
> spec. Return findings in the schema from `findings-schema.md`. Every finding needs evidence: the
> proof required by the evidence rule in `findings-schema.md`; a finding without proof is
> `unverified`. No findings is a valid answer.

## REUSE

Does the diff re-implement something that already exists? Search the repo (and declared
dependencies) for existing helpers, types, constants, fixtures, and utilities that do the same job.
Flag each new function, type, or test helper that duplicates one, and name the existing one to use.
Not in scope: whether the new code is simple, fast, or well placed.

## SIMPLIFICATION

Could the same behaviour be expressed with less? Look for speculative generality (config or
abstractions with one caller), needless indirection, dead branches, state that can be derived, guards
for states the flow already rules out, and code that grew past what the spec asks. Propose the
smaller form. Not in scope: duplication of existing code (REUSE) or runtime cost (EFFICIENCY).

## EFFICIENCY

Is there avoidable cost on a path that matters? Look for work repeated in a loop, accidental
quadratic scans, unbounded allocation or growth, missing batching or caching where the surrounding
code already uses it, blocking calls in latency-sensitive paths, and needless I/O. State the
expected scale and the cost, or say you could not measure. Do not flag micro-optimisations on cold
paths. Not in scope: readability or placement.

## ALTITUDE

Is the change at the right level of the system? Check that it fixes the cause rather than the
symptom, lives in the module that owns the concern, matches the abstraction level of its neighbours,
and does not leak a lower-level detail upward or push a policy decision down into a utility. Check
that the interface the block exposes matches what the spec promises and no more. Not in scope:
line-level style, cost, or duplication.

## STALENESS

Did a subsystem's code change without a matching change to its documentation? Read the diff and the
project's `docs/` (ADRs in `docs/decisions/*.md`, `docs/spec.md`, diagrams), and
`.agents/iterations/` if it exists. For each changed subsystem, find its ADR, its `docs/spec.md`
section, and its diagram. Flag each one that the diff leaves unchanged while the code now disagrees
with it.

A finding is: changed behaviour, changed structure (modules, boundaries, data flow), or a changed or
reversed recorded decision, with no matching change to the ADR, spec section, or diagram that
describes it. Name the doc, the section, and the code change it no longer matches.

Not a finding: a refactor with no behaviour change, a test-only change, a formatting or rename-only
change, or code that has no doc describing it. A missing doc for new code is not staleness.

Every finding needs the evidence rule in `findings-schema.md`: cite the doc `file:line` and the code
`file:line` that contradict each other, with the reasoning chain. Otherwise set `status:
"unverified"`. Use `angle: "staleness"`. Not in scope: doc wording or style, or code quality.

## Comment quality (separate reviewer)

Read the `code-quality` skill's `references/comment-rubric.md` and judge the changed files against
it. Return findings with `angle: "comments"`, the comment's excerpt as `evidence`, and the
replacement wording as `suggested_fix`.
