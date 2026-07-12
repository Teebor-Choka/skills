---
name: forge-idea
description: >
  Forge a rough idea, thesis, or plan into a viable one through cooperative,
  research-driven iteration. It interrogates the premise hard, decomposes it into
  load-bearing branches, fans out independent agents to stress-test each branch,
  then prunes the dead branches and reshapes the rest with what the research found —
  looping with the user until the idea stabilizes or they stop. Use whenever the
  user wants to pressure-test, validate, red-team, kill-test, gut-check, poke holes
  in, evolve, refine, or find the viable version of a business thesis, product
  direction, technical architecture choice, strategy, or research hypothesis —
  especially when they say "will this actually work", "is this defensible", "tear
  this apart", "why would this fail", "how do I make this work", "what's the wedge",
  or "should we build X". Also trigger when a premise developed in the conversation
  is ready to be tested against reality. Prefer this over an ad-hoc research pass
  whenever the goal is to harden or reshape a specific premise, not open-ended learning.
---

# Forge Idea

A repeatable harness for hammering a rough premise into a viable one. It is
cooperative, not destructive: research aggressively **prunes dead branches** but
feeds every surviving edge back to **reshape the idea**. The aggression lives at the
branch level — a branch that can't be defended gets cut without mercy — while the
idea itself is nurtured toward a version that survives. The user is the smith: each
round ends with them, and they decide whether to stop, redirect, or forge again.

The most valuable output is rarely the original premise intact — it is the evolved
premise, and the viable variants the pruning revealed.

## When this fits

Any premise with claims concrete enough to test: a business/venture thesis, product
direction, architecture choice, strategic bet, research hypothesis, a "we should do X
because Y" argument. If the premise is vague, the interrogation step (below) sharpens
it before any fan-out — the agents need falsifiable claims to work on.

Scale rigor to the ask. Quick gut-check = 3 agents, one round, Agent fan-out. "Tear
this apart / thoroughly / keep going" = 5–6 agents and multiple rounds. Read
`references/forge-tactics.md` before briefing agents and `references/forge-report.md`
before writing the report.

## The loop

### 1. Interrogate — grill the premise hard

Do **not** just restate it and ask for a nod. Interrogate until it is sharp, pushing
back on every soft answer:

- **Buyer/user** — who *exactly* feels this pain, and who pays? Name them.
- **Mechanism** — *why* does this actually work? What has to be true for the value
  to exist at all?
- **Success metric** — what observable outcome would prove it worked?
- **Riskiest belief** — which single assumption, if wrong, collapses everything?
- **Hidden assumptions** — what is being taken for granted about demand, cost,
  timing, or capability?

Convert the answers into **falsifiable load-bearing claims** — the things that must
all be true. State them back. Iterate with the user until they hold up; a squad
pointed at fuzzy claims wastes the whole run.

### 2. Ground with research

Invoke the **`deep-research` skill** on the core concepts — key terms, named
technologies, the market category — to build a shared factual floor: who already
operates here, the prior art, the landscape. A crowded field is **demand evidence**,
not a closed door (see forge-tactics). Feed a condensed grounding into each agent's
brief. For a light gut-check you may let each agent research its own branch directly.

### 3. Decompose into branches

Map the load-bearing claims onto 3–6 **branches** — one per agent, derived from the
premise, each independently testable so agents don't overlap.
`references/forge-tactics.md` lists the evidence classes (prior-art, incumbents &
lane, funding/M&A comps, demand reality, timing/regulatory, economics,
feasibility/team, second-order failure modes) — pick the ones this premise rests on.

### 4. Fan out the stress-test squad (independent)

Spawn one agent per branch **in a single message so they run concurrently** and
independently — they must not see each other's work; independent convergence is the
signal. Each agent attacks its branch hard **and reports constructively** (mandate
verbatim in forge-tactics):

- **Verdict** — SURVIVES / ADAPT / PRUNE, with which failure mode (false /
  irrelevant / already-owned).
- **The evidence** — the single most damaging cited finding (named product, paper,
  funding round, regulation-with-date, benchmark number).
- **The adaptation** — how the idea should change given the finding.
- **The surviving edge** — the strongest version of the claim the finding doesn't reach.
- **Opportunity signals** — incumbent holes mined from reviews / complaints / forums /
  churn, unmet demand, wedge openings.

**Engine scales by rigor.** Default: `general-purpose` Agent fan-out (they web-research
and can invoke `deep-research` scoped to their branch). For a deep "be thorough" run,
use the `Workflow` tool for a deterministic find → adapt → prune → re-test loop — this
skill authorizes it.

### 5. Prune & reshape

Cut PRUNE branches without mercy — record them as dead ends so they aren't revisited.
Apply the ADAPT adaptations and fold in the opportunity signals to produce an
**evolved premise**. Surface any emergent variants or wedges the pruning revealed.
Note where agents converged (high confidence) and where they split (the split is
itself a finding — surface it, don't average it).

### 6. Smith checkpoint — hand it back to the user

Present, concisely: the evolved premise, what was pruned and why, emergent
variants/wedges, and the open questions. Then the user decides:

- **Stop** — the idea is viable enough, or clearly dead.
- **Keep this direction** — forge another round on the evolved premise.
- **Redirect** — pursue one of the variants instead.

This checkpoint is the cooperative core — the user's steer drives the next round.

### 7. Iterate

If continuing, re-test only the **materially-changed or newly-introduced** branches
(carry forward what already SURVIVED). Loop steps 4–6 until the premise stabilizes
(a full round changes nothing) or the user stops.

### 8. Report

Follow `references/forge-report.md`: bottom line first, branch scorecard, per-branch
findings, the **evolution trail** (premise vN → vN+1, what each round changed),
ranked **viable variants**, pruned dead ends, and honest caveats. Write it to a
markdown file (working directory or a location the user names).

## What makes this different from a normal research pass

- **Prune branches, forge the idea.** The burden of proof is on each claim, but a
  failed claim reshapes the idea rather than ending it.
- **Research drives evolution.** Findings don't just score the premise — they change it.
- **Cooperative and human-in-the-loop.** The user steers at every round; the loop
  bends to their judgment, not the other way around.
- **Willing to conclude either way.** A branch that survives the strongest attack is
  SURVIVES, honestly. An idea with no surviving branch and no live variant is DROP,
  honestly. Never manufacture a prune, never manufacture a save.
