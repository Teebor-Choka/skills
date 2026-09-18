# Comparative / judge-panel mode — choosing among N options

Load this when the forge question is _"which of N options wins?"_ rather than _"is this
premise viable?"_. It replaces the default branch-mode behavior at the fan-out and
synthesis steps; everything else in `SKILL.md` still applies. Read it before decomposing.

## Choose the fan-out mode — branch vs comparative

The decompose→fan-out machinery runs in one of two modes; pick by the shape of the question.

- **Branch mode (default).** The question is _"is this premise viable?"_ One load-bearing
  **claim** per agent; each returns the `VIABLE / ADAPT / PRUNE` verdict in
  `references/forge-verdict.schema.json`. Steps 3–8 are written for this mode.
- **Comparative / judge-panel mode.** The question is _"which of N options wins?"_ — a beachhead,
  a wedge, an entry angle, a domain, a monetization model. One **candidate** per agent, each
  scored on the **same shared criteria**, returning `references/forge-compare.schema.json`. Add
  **one cross-cutting _decider_ agent** that ranks all options on the single criterion most likely
  to break the tie (budget-now, reachability, distribution, defensibility) and returns a brief
  **ranked list** of the options on that one dimension (prose — not the per-candidate schema); in
  practice the decider, not the per-candidate agents, picks the winner. The synthesis **ranks**; it does not
  prune. Do **not** force `VIABLE/ADAPT/PRUNE` onto options — that axis measures "does a claim
  hold," not "which is best," and collapses to a useless all-`ADAPT` result when misapplied.

The modes compose across rounds: a branch-mode forge often ends by surfacing several viable
variants, and choosing among them is a comparative-mode round.

## How the mode changes each step

- **Step 4 (fan out the squad).** Comparative mode returns `forge-compare.schema.json` instead
  of the branch verdict schema.
- **Step 5 (prune & reshape).** In comparative mode this step is a _ranking_, not a pruning:
  there are no branches to cut — order the scored candidates, let the decider's tie-breaker
  settle close calls, and fold strategic fit into the shared criteria rather than running a
  separate FIT/STRETCH pass.
- **Step 6 (smith checkpoint).** In comparative mode, present the ranking and the winner's
  rationale — what ranked where and why — rather than what was pruned.
- **Step 7 (persist to the idea file).** Use a `## Comparative scorecard` instead of the
  `## Branch scorecard`, and omit the `## Strategic fit` section — fit folds into the shared
  criteria. See the comparative scorecard in `references/forge-report.md`.
