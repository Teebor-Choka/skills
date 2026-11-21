---
name: by-angle
description: >
  Gate a finished spec block with four parallel reviewers (REUSE, SIMPLIFICATION,
  EFFICIENCY, ALTITUDE) after a red-first build: "implement Block N", "run the review
  angles". Not for one-off diffs (use code-review).
license: MIT
compatibility: any
metadata:
  version: "1.1.0"
---

# by-angle

One repeatable loop per block of a spec: **tests first, implement, review read-only, fix, repeat
until clean.** It packages the orchestration that otherwise gets re-written every block.

A _block_ is a unit with a written spec, one write-set, and a checkable "done" (see the `architect`
skill's spec blocks). If there is no spec, write the acceptance criteria first; the roles below
need something to be red against.

## Roles

| Role              | Sees                               | Does                                             | Must not                                          |
| ----------------- | ---------------------------------- | ------------------------------------------------ | ------------------------------------------------- |
| **test-author**   | block spec, public interfaces      | writes tests for positive and adversarial cases  | read or write the implementation                  |
| **implementer**   | block spec, the red tests          | least code that turns them green, then refactors | edit the tests to pass (a bad test is a finding)  |
| **reviewer** (xN) | block spec, diff, repo (read-only) | judges the diff from one angle, returns findings | edit, format, commit, or run anything that writes |

Test-author and implementer are separate agents or separate contexts, so the tests do not echo the
implementation's mistakes. The orchestrator (you) owns dispatch, triage, and every edit that
follows a review.

## The block loop

1. **Red.** Test-author writes the tests from the spec. Run them; capture the failing output. A test
   that passes before any implementation exists is wrong or vacuous: fix it before moving on.
   Include a test for the bad behaviour (a silent no-op must fail visibly).
2. **Green.** Implementer makes the suite pass with the least code, then refactors under green. It
   reports the commands it ran and their results.
3. **Review.** Dispatch the reviewers in parallel (next section), then triage the merged findings.
4. **Fix.** Implementer addresses each `blocker` and `major` finding; `minor` and `nit` are the
   orchestrator's call. Reviewers never apply fixes.
5. **Re-review** only the angles that produced a finding. Stop at zero blockers/majors, or after
   two fix rounds, then escalate the remainder to a human. More rounds rarely converge.

## The angles

Run five reviewers in one parallel batch, each in a fresh read-only context:

- Four **angle** reviewers: REUSE, SIMPLIFICATION, EFFICIENCY, ALTITUDE. Add the STALENESS angle
  when the project has a `docs/` directory. Each prompt ends with
  "this angle only; ignore everything outside it". Angle briefs are in
  [references/angles.md](references/angles.md).
- One **comment-quality** reviewer, which reads the `code-quality` skill's
  `references/comment-rubric.md` and judges the changed files against it. Do not copy the rubric
  here; point the reviewer at it. For numeric risk (complexity, coverage, duplication) run
  `code-quality` itself instead of asking an angle reviewer to guess.

**Reviewers are read-only.** Give them read tools only (read, search, list, git/gh read commands),
no edit, write, or shell-with-side-effects tool, and say so in the prompt: "report only, do not
modify any file". Enforce it by tool allowlist or sandbox, not by instruction alone; per-host
bindings are in `code-quality/references/cross-agent.md` and the `models:extension-author` platform notes. If
a reviewer's output includes a patch, treat it as a suggested fix inside a finding, never apply it
blind.

Each reviewer returns findings in the schema in
[references/findings-schema.md](references/findings-schema.md), which also holds the evidence rule
for what counts as proof. Triage: merge duplicates across
angles, and verify each `proven` `blocker` by reading the cited code before acting. A finding
without proof is `unverified`: report it, but it cannot block a merge. The evidence rule is in the
findings schema. No findings is a valid result; do not prompt a
reviewer to find something.

**Tier and depth.** Run a reviewer on the top tier only when the diff touches security, unsafe,
auth or secrets, or exceeds about 400 changed lines. Otherwise use the Execution tier. A re-review
after rework covers only the delta. The coordinator hands a reviewer the PR number or diff range
and does not read a large diff itself.

## Several blocks

Hand the dependency and write-set analysis to the `graph-engine` skill. It returns waves of blocks
with disjoint write-sets, the critical path, and barriers. Run the block loop per block, in parallel
within a wave, then do one **serial integration pass** after each wave (merge, full test run, one
angle review over the combined diff). Isolated block contexts do not integrate themselves. A single
block needs no graph.

## Related skills

- `simplify` and `code-review` review a single diff once; this skill adds the red-first roles, the
  block loop, and the findings contract around the same four angles.
- `code-quality` supplies the comment rubric and the numeric audit.
- `architect` produces the block specs this loop consumes.
