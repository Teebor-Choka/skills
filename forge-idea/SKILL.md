---
name: forge-idea
description: >
  Forge a rough idea, thesis, or plan into a viable one through cooperative,
  research-driven iteration. It interrogates the premise hard, reduces it to a
  sharp minimal kernel, decomposes that kernel into load-bearing branches, fans
  out independent agents to stress-test each branch, then prunes the dead branches
  and reshapes the rest with what the research found — looping with the user until
  the idea stabilizes or they stop. Use whenever the user wants to pressure-test,
  validate, red-team, kill-test, gut-check, poke holes in, evolve, refine, or find
  the viable version of a business thesis, product direction, technical architecture
  choice, strategy, or research hypothesis — especially when they say "will this
  actually work", "is this defensible", "tear this apart", "why would this fail",
  "how do I make this work", "what's the wedge", or "should we build X". Also trigger
  when a premise developed in the conversation is ready to be tested against reality.
  Prefer this over an ad-hoc research pass whenever the goal is to harden or reshape
  a specific premise, not open-ended learning.
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

Scale rigor to the ask. Quick gut-check = one branch (the riskiest), one round, Agent
fan-out. "Tear this apart / thoroughly / keep going" = 5–6 branches and multiple
rounds. Read `references/forge-tactics.md` before briefing agents and
`references/forge-report.md` before persisting the result. The verdict schema agents
return is `references/forge-verdict.schema.json`.

## Writing discipline (applies to the whole idea file)

Stay **sharp**. Every claim is carefully worded so its intent is unambiguous, and
compact so it loses no information value. Never soften a claim into fuzz to hedge —
uncertainty is carried by the **confidence tag**, not by vague language. A reader must
be able to tell exactly what is being asserted and how well it is grounded.

Confidence tags (borrowed from the landscape briefs; put one on every non-obvious
claim): **[Established]** (multi-source) · **[Reported]** (single/secondary source) ·
**[Vendor/Projection]** (marketing/forecast) · **[Contested]** · **[Open]** (unresolved).

## The loop

### 0. Detect context — file or report

If invoked in a repo with an ideas pipeline (a directory of idea markdown files, e.g.
state subdirectories like `raw/ explored/ decided/` with YAML frontmatter), forge
operates **on the idea's file** — it reads any prior forge output there and writes its
result back into that file (step 7). If the target file has no `state` frontmatter,
**bootstrap it**: add the frontmatter and the section structure so the file becomes a
first-class pipeline artifact. If there is no pipeline at all, forge degrades to a
standalone report written to the working directory.

Forge is pipeline-**aware** but pipeline-**passive**: it reads and writes file
*content*, but it **never mutates `state` or `verdict` frontmatter**. Promoting an idea
`raw → explored → decided` (and writing a `pursue/park/kill` verdict) is always the
user's manual call at the smith checkpoint. Forge only *recommends* the transition.

### 1. Interrogate → reduce to the kernel

Do **not** just restate the premise and ask for a nod. Interrogate until it is sharp,
pushing back on every soft answer:

- **Target** — who or what is this *for*? Name it explicitly. (Not necessarily a
  paying buyer — the idea may be a research bet or an internal tool; but the target
  must be named.)
- **Why / mechanism** — *why* does this actually work? What has to be true for the
  value to exist at all? The Why must come out of the interrogation.
- **Success metric** — what observable outcome would prove it worked?
- **Riskiest belief** — which single assumption, if wrong, collapses everything?
- **Hidden assumptions** — what is taken for granted about demand, cost, timing, or
  capability?

Then **reduce to the kernel**: the single sharpest, minimal, falsifiable form of the
idea — the smallest claim that, if it survives, keeps the idea alive. The kernel is
what localizes the research: a broad premise gives the agents no coordinates and they
return a generic landscape; a sharp kernel gives them a specific target they can
falsify. Reduction is **focus, not amputation** — the scope you strip off is **parked**
as an `## Expansion (parked)` note in the file, never deleted. Nothing is cut without
evidence; the kernel is only what you test *first*.

- **Interactive mode** (user is present): multi-turn grill, iterate on the kernel
  until it holds up.
- **Async / remote mode** (fired without the user at the keyboard): infer the kernel
  from the note, state it as a single sentence, and **stop at the confirm-the-kernel
  gate** — present the one-line kernel and wait for a thumbs-up or correction before
  spending any tokens on the fan-out. Cheap to confirm, expensive to aim wrong.

### 2. Ground with research (conditional)

Build a shared factual floor before decomposing:

- **Raw idea** (no prior research): invoke the **`deep-research` skill** on the core
  concepts — key terms, named technologies, the market category — and condense a
  grounding into each agent's brief.
- **Already-explored idea** (a prior brief exists in the file): read that brief as the
  floor and research only the **deltas** since its date — what changed, what's new.
  Don't re-run deep-research to rediscover what's already written.

A crowded field is **demand evidence**, not a closed door (see forge-tactics).

### 3. Decompose the kernel into localized branches

Map the kernel's load-bearing claims onto **branches** — one per agent, each
independently testable and aimed at concrete coordinates so search returns signal, not
a landscape dump. `references/forge-tactics.md` lists the evidence classes (prior-art,
incumbents & lane, funding/M&A comps, demand reality, timing/regulatory, economics,
feasibility/team, second-order failure modes) — pick the ones this kernel rests on.

- **Full forge:** 3–6 branches, fanned out concurrently.
- **Async gut-check:** test the **single riskiest branch first**; only fan out the
  rest if it survives. Serial, cheap, fails fast.

### 4. Fan out the stress-test squad (independent, structured)

Spawn one agent per branch **in a single message so they run concurrently** and
independently — they must not see each other's work; independent convergence is the
signal. Each agent attacks its branch hard **and reports constructively**, returning
the structured verdict in `references/forge-verdict.schema.json`:

- **verdict** — VIABLE / ADAPT / PRUNE, with the failure mode (false / irrelevant /
  already-owned).
- **most_damaging_finding** — the single most damaging cited finding (named product,
  paper, funding round, regulation-with-date, benchmark number), with source and
  confidence tag.
- **adaptation** — how the idea should change given the finding.
- **surviving_edge** — the strongest version of the claim the finding doesn't reach.
- **opportunity_signals** — incumbent holes mined from reviews / complaints / forums /
  churn, unmet demand, wedge openings.

The mandate to put in every agent's brief is verbatim in `forge-tactics.md`.

**Engine scales by rigor.** Default: `general-purpose` Agent fan-out (they web-research
and can invoke `deep-research` scoped to their branch). For a deep "be thorough" run,
use the `Workflow` tool for a deterministic find → adapt → prune → re-test loop, with
the schema above as the agents' `StructuredOutput` — this skill authorizes it.

**Cost guardrail.** Watch the double fan-out (grounding deep-research + per-branch
agents each possibly invoking deep-research):
- *Gut-check:* 1 branch, 1 round, **no** nested deep-research.
- *Thorough:* 5–6 branches, Workflow, nested deep-research allowed.
The confirm-the-kernel gate exists so a mis-aimed kernel never burns a full fan-out.

### 5. Prune & reshape — grounded, plural, not radical

Cut PRUNE branches without mercy — record them in the dead-ends ledger so they aren't
revisited. Apply the ADAPT adaptations and fold in the opportunity signals. But **do
not lurch**: keep the reshaping **grounded and incremental**, and present **several
grounded options** for where the idea could go rather than one radical pivot. Note
where agents converged (high confidence) and where they split (the split is itself a
finding — surface it, don't average it). The reshaping proposes; the smith checkpoint
decides which option to converge on.

### 6. Smith checkpoint — hand it back to the user

Present, concisely: the evolved premise (and the grounded options from step 5), what
was pruned and why, emergent variants/wedges, the open questions, **and a recommended
pipeline transition** (e.g. "promote raw → explored", "this reads like decided:kill").
Then the user decides:

- **Stop** — the idea is viable enough, or clearly dead.
- **Keep this direction** — forge another round on the evolved premise.
- **Redirect** — pursue one of the variants/options instead.

Forge does not apply the transition or write a verdict itself — the user does. This
checkpoint is the cooperative core; the user's steer drives the next round.

### 7. Persist to the idea file

Write the result into the idea file (or standalone report if no pipeline), following
`references/forge-report.md`. Body sections — the frontmatter `state`/`verdict` stay
untouched:

- evolved premise + the current kernel
- `## Branch scorecard`
- `## Evolution` — the v0 → v1 → … trail (what each round changed and why)
- `## Dead ends` — the pruned-branch ledger, so they aren't revisited
- `## Viable variants` — ranked, most-alive first
- `## Expansion (parked)` — the scope reduction stripped off
- `## Caveats`

This makes re-forging **resumable**: next round diffs against last round instead of
restarting.

### 8. Iterate

If continuing, re-test only the **materially-changed or newly-introduced** branches
(carry forward what already came back VIABLE). Loop steps 4–6 until the premise
stabilizes (a full round changes nothing) or the user stops. The idea file body is the
living report.

## What makes this different from a normal research pass

- **Prune branches, forge the idea.** The burden of proof is on each claim, but a
  failed claim reshapes the idea rather than ending it.
- **Sharp kernel, localized research.** The idea is reduced to a minimal falsifiable
  kernel so the fan-out has coordinates and returns signal, not a landscape.
- **Research drives evolution — grounded, not radical.** Findings change the idea, but
  incrementally and in plural options; the smith drives convergence.
- **Cooperative and human-in-the-loop.** The user steers at every round and owns every
  pipeline-state transition; the loop bends to their judgment.
- **Willing to conclude either way.** A branch that survives the strongest attack is
  VIABLE, honestly. An idea with no surviving branch and no live variant is DROP,
  honestly. Never manufacture a prune, never manufacture a save.
