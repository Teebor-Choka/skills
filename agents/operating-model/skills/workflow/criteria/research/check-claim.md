# Rubric: one claim check

The judge reads the claim, its sources and the checker's output. The check passes only when every rule
holds. A `hearsay`, `refuted` or `unreachable` verdict can pass: this rubric judges the check, not the claim.

1. The verdict is one of `verified`, `hearsay`, `refuted`, `unreachable`.
2. `verified` is given only when a cited primary source states the claim, and the evidence quotes it.
3. `refuted` names the source that contradicts the claim.
4. `unreachable` is given only when no cited URL could be opened, and the evidence says what failed.
5. The evidence is about this claim and its cited sources, not about other sources.

## On a fail

Report the claim id, the number of each rule that fails, and the verdict the judge would give instead, with
one sentence of evidence.
