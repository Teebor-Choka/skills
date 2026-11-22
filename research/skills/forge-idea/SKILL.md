---
name: forge-idea
description: >
  Stress-test a rough idea or plan until a viable version remains. Use for
  "will this work", "tear this apart", "red-team", "is this defensible",
  "should we build X", "what's the wedge". Not for fact-finding or settled
  decisions.
---

# Forge Idea

A repeatable harness for hammering a rough premise into a viable one. It is
cooperative, not destructive: research aggressively **prunes dead branches** but
feeds every surviving edge back to **reshape the idea**. The aggression lives at the
branch level: a branch that can't be defended gets cut without mercy, while the
idea itself is nurtured toward a version that survives. The user is the smith: each
round ends with them, and they decide whether to stop, redirect, or forge again.

Usually the most valuable output is not the original premise intact but the evolved
premise, plus the viable variants the pruning revealed.

## When this fits

Any premise with claims concrete enough to test: a business/venture thesis, product
direction, architecture choice, strategic bet, research hypothesis, a "we should do X
because Y" argument. If the premise is vague, the interrogation step (below) sharpens
it before any fan-out — the agents need falsifiable claims to work on.

Scale rigor to the ask. Quick gut-check = one branch (the riskiest), one round, a single
fan-out. "Tear this apart / thoroughly / keep going" = 5–6 branches and multiple
rounds. Read `references/forge-tactics.md` before briefing agents,
`references/cross-agent.md` before spawning them (how to run the fan-out natively on
Claude Code, Codex, or OpenCode), and `references/forge-report.md` before persisting the
result. The verdict schema agents return is `references/forge-verdict.schema.json`; for
comparative (which-option-wins) rounds they return
`references/forge-compare.schema.json` (step 3b).

Read `references/forge-principles.md` when writing any claim into the idea file (writing discipline and confidence tags).

## The loop

The steps below are written for the default **branch mode** ("is this premise viable?").
Comparative / judge-panel mode ("which of N options wins?" — rank candidates on shared
criteria with a decider tie-break, no pruning): read `references/forge-comparative.md`
before decomposing.

### 0. Detect context — file or report

If invoked in a repo with an ideas pipeline (a directory of idea markdown files with
YAML frontmatter — e.g. stage-prefixed flat files like `raw-*.md` / `explored-*.md`, or
state subdirectories like `raw/ explored/ decided/`), forge operates **on the idea's
file** — it reads any prior forge output there and writes its result back into that file
(step 7). If the target file has no `state` frontmatter,
**bootstrap it**: add the frontmatter and the section structure so the file becomes a
first-class pipeline artifact. If there is no pipeline at all, forge degrades to a
standalone report written to the working directory.

Forge reads and writes file _content_, but it **never mutates `state` or `verdict`
frontmatter**. Promoting an idea
`raw → explored → decided` (and writing a `pursue/park/kill` verdict) is always the
user's manual call at the smith checkpoint. Forge only _recommends_ the transition.

### 1. Interrogate → reduce to the kernel

Read `references/forge-loop-detail.md` (Step 1) for the interrogation questions, the kernel reduction and the interactive vs async modes. Interrogate until the kernel is sharp; at minimum name target, mechanism, success metric and riskiest belief.

### 2. Ground with research (conditional)

Build a shared factual floor before decomposing:

- **Raw idea** (no prior research): run a **deep research pass** on the core
  concepts (key terms, named technologies, the market category) and condense a
  grounding into each agent's brief. Delegate this to a dedicated research skill or
  subagent where the agent provides one (`references/cross-agent.md`).
- **Already-explored idea** (a prior brief exists in the file): read that brief as the
  floor and research only the **deltas** since its date — what changed, what's new.
  Don't re-run deep-research to rediscover what's already written.

A crowded field is **demand evidence**, not a closed door (see forge-tactics).

### 3. Decompose the kernel into localized branches

Map the kernel's load-bearing claims onto **branches** — one per agent, each
independently testable and aimed at concrete coordinates so search returns signal, not
a landscape dump. `references/forge-tactics.md` lists the evidence classes (prior-art,
incumbents & lane, funding/M&A comps, demand reality, timing/regulatory, economics,
feasibility/team, second-order failure modes); pick the ones this kernel rests on.

- **Full forge:** 3–6 branches, fanned out concurrently.
- **Async gut-check:** test the **single riskiest branch first**; only fan out the
  rest if it survives. Serial, cheap, fails fast.

### 3b. Choose the fan-out mode — branch vs comparative

Branch mode (the default, steps 3–8) tests one load-bearing claim per agent. If the question
is "which of N options wins?", switch to comparative / judge-panel mode — read
`references/forge-comparative.md` before decomposing.

### 4. Fan out the stress-test squad (independent, structured)

Read `references/forge-loop-detail.md` (Step 4) for the agent verdict fields, engine scaling and the cost guardrail. Spawn one agent per branch concurrently and independently; each returns `references/forge-verdict.schema.json`.

### 5. Prune & reshape — grounded and plural

Read `references/forge-loop-detail.md` (Step 5) for pruning, plural reshaping, the diverge step and strategic-fit scoring.

### 6. Smith checkpoint — hand it back to the user

Read `references/forge-loop-detail.md` (Step 6) for what to present and the Stop / Keep / Redirect / Fork options.

### 7. Persist to the idea file

Write the result into the idea file (or standalone report if no pipeline), following
`references/forge-report.md`. Body sections — the frontmatter `state`/`verdict` stay
untouched:

- evolved premise + the current kernel (with a `**Lineage:**` pointer if this idea was forked
  from another — see `references/forge-report.md`)
- `## Branch scorecard`
- `## Strategic fit` — the scored fit-against-target block (only if fit criteria were
  captured; omit for open-ended bets)
- `## Evolution` — the v0 → v1 → … trail (what each round changed and why)
- `## Dead ends` — the pruned-branch ledger, so they aren't revisited
- `## Viable variants` — ranked, most-alive first
- `## Expansion (parked)` — the scope reduction stripped off
- `## Caveats`

This makes re-forging **resumable**: next round diffs against last round instead of
restarting.

### 8. Iterate

Running a second round: read `references/forge-iterate.md` before re-forging.

## What makes this different from a normal research pass

Read `references/forge-principles.md` for what separates forge from a normal research pass.
