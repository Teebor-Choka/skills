# Forge Tactics — the stress-test playbook

This is the ammunition each agent uses. The job is not a fair review, and not blind
destruction — it is to attack a single branch hard, cut it if it can't be defended,
and report back **what survives and how the idea should adapt**. A branch that holds
under a genuine attack is worth building on; one that only holds under a polite review
is not, because reality is not polite. But the aggression is aimed at the _branch_,
never at the idea as a whole.

## The mandate (put this in every agent's brief)

> You are assigned ONE load-bearing branch of this idea. Attack it hard: try to prove
> the underlying claim false, irrelevant, or already-owned, and cut it without mercy
> if it cannot be defended. But your job is to make the idea _better_, not to kill it.
> Return the structured verdict (`references/forge-verdict.schema.json`): the verdict
> — VIABLE / ADAPT / PRUNE — with its failure mode; the single most damaging cited
> finding; the adaptation (how the idea should change given what you found, grounded
> and incremental — reshape, don't lurch); the surviving edge the finding doesn't
> reach; and any opportunity signals. Ground every non-obvious assertion in a real,
> cited source with a confidence tag. Prune dead branches aggressively; never prune
> the idea itself.

## The three ways a branch fails

Name which one in the finding — it determines the adaptation:

1. **False** — factually wrong (the thing doesn't work, the number is off). → adapt
   by dropping the false mechanism and finding what does move the outcome.
2. **True but irrelevant** — holds but doesn't change the result (an edge nobody pays
   for). → adapt by re-anchoring to an edge the buyer actually ranks.
3. **True but already owned** — holds but an incumbent / open-source project /
   standards body / vendor already owns it. → adapt by finding the seam they _don't_
   own (see "crowded is demand" and "mine the holes" below).

## Two corrections to reset before you start

These are the assumptions agents get wrong most often. Bake them in:

- **A crowded field is demand, not a wall.** Fifteen organizations doing something
  similar proves people pay for it — the problem is real and monetized. Do not read
  "many competitors" as "market full." Quantify the pull (funding, users, spend) and
  ask where it is _underserved_, not whether to enter.
- **Every incumbent has holes → a wedge.** No shipped product satisfies everyone.
  The move is to find what existing customers wanted and didn't get: mine reviews
  (App Store, G2, Trustpilot, Amazon), blogs, forums (Reddit, HN), support threads,
  and churn/"switched away because…" posts. Recurring complaints are a positioning
  map. A niche wedge is usually hiding in an incumbent's one-star reviews.

## Evidence classes to hunt (pick the ones the branch rests on)

Don't run all of these blindly — the premise dictates which matter.

- **Prior art / it-already-exists** — papers, open-source repos, shipped products.
  Note license; copyleft/non-commercial prior art changes the adaptation, not just
  the verdict.
- **Incumbents & competitive lane** — who occupies the exact intersection now, when
  they shipped, how well-capitalized, and — critically — where they're weak.
- **Funding & M&A comps** — what got raised and acquired, and for how much. Reveals
  the realistic ceiling and whether sub-scale players got a premium or an acqui-hire.
- **Demand reality** — a budget line, or only anxiety? Distinguish "people worry
  about X" from "people have a line item for X"; watch for demand for the funnel
  (audits, pilots) mistaken for demand for the thing.
- **Timing / regulatory** — verify the exact date, scope, and whether a cited
  regulation actually mandates _this_ mechanism (regulations mandate outcomes, not
  your solution).
- **Economics / unit model** — does the money work at the stated scale and team size?
- **Feasibility / team** — can this team build/sell/certify this in the stated time?
- **Second-order & failure modes** — what breaks after it works: approval fatigue,
  cold-start, trust paradox, cannibalization, adoption friction.

## Convergence is the signal

Run agents independently — never let them see each other's work mid-flight. When
independent skeptics converge without coordinating, that is far stronger than one
opinion. When they split, the split _is_ the finding — surface it, don't average it.

Convergence also operates **across rounds**, not just within a fan-out. A variant that was
parked or set aside in one round and then **independently reappears from a different attack
angle** in a later round is _triangulation_ — the highest-confidence signal the harness can
produce, stronger than any single-round agreement. Watch the `## Viable variants` and
`## Expansion (parked)` ledgers for recurrence; a survivor that keeps re-emerging on its own is
usually the real idea, and should be elevated over anything freshly generated.

## Honesty discipline

- Cite every non-obvious claim, and tag its confidence: **[Established]** (multi-source)
  · **[Reported]** (single/secondary) · **[Vendor/Projection]** (marketing/forecast) ·
  **[Contested]** · **[Open]** (unresolved). Aggregator/press/vendor figures are fine
  but tag them accordingly; the _direction_ should be robust across independent sources.
- Distinguish verified from inferred. An inferred white space is a lead to validate
  with real conversations, not a proven fact — say so, and tag it [Open].
- Stay sharp. Word every claim so its intent is unambiguous; carry uncertainty in the
  confidence tag, never by softening the claim into fuzz.
- Never manufacture a prune, and never manufacture a save. If a branch genuinely
  survives, VIABLE is the honest verdict; if it's genuinely dead, cut it. The
  squad's credibility depends on being willing to land on either.
