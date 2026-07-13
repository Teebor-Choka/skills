# Forge Report Template

The forge result is written into the **idea file** (see SKILL step 7) — these sections
become the body of that file, below its frontmatter. When there is no ideas pipeline,
write the same skeleton to a standalone markdown file in the working directory.

Do **not** touch the frontmatter `state` / `verdict` — forge is pipeline-passive; the
user promotes the idea and writes the verdict manually. If the file has no frontmatter
at all, bootstrap it (see below), still without deciding the state for the user.

Adapt headings to the premise, but keep the skeleton. Order matters: decision first
(the reader gets the answer before the evidence), scorecard second, then the drill-down,
the evolution trail, and the persisted ledgers.

---

```markdown
---
# bootstrap this block only if the file has no frontmatter; leave an existing one alone
domain: <kebab-domain>
title: <Idea name>
state: <raw|explored|decided> # forge recommends, user sets — never auto-change
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
author: <name>
---

# <Idea name> — Forge Report (<YYYY-MM>)

<One paragraph: the premise as it stands now and its load-bearing claims. Name the
method: "N independent agents, one per branch, each attacking its branch and returning
a structured adaptation; every non-obvious claim source-cited and confidence-tagged;
M rounds of forging.">

## Kernel

<The current minimal falsifiable kernel — the sharpest one-sentence form of the idea:
the explicit target (who/what it's for) and the Why (mechanism). This is what the
research was aimed at.>

## Bottom line

<2–4 sentences. Lead with the recommendation — PROCEED / EVOLVE / DROP. Say whether the
agents converged or split, how far the idea moved, and the recommended pipeline
transition (e.g. "promote raw → explored").>

> **<RECOMMENDATION> — <one-line reason>**

## Branch scorecard

| Branch                 | Verdict                    | Key finding & adaptation                                                      |
| ---------------------- | -------------------------- | ----------------------------------------------------------------------------- |
| <load-bearing claim 1> | **VIABLE / ADAPT / PRUNE** | <most damaging evidence + how the idea changed, with source + confidence tag> |
| <load-bearing claim 2> | ...                        | ...                                                                           |

Tally: **VIABLE ×N · ADAPT ×N · PRUNE ×N**

## Per-branch findings

### <Branch 1> — <verdict>

<The attack: named incumbents / prior art / data / dates that falsify or weaken the
claim, each cited and confidence-tagged. Then the ADAPTATION (grounded, incremental)
and the SURVIVING EDGE the finding doesn't reach. Distinguish false / true-but-irrelevant
/ true-but-already-owned. If PRUNE, say plainly why it's a dead end.>

### <Branch 2> — <verdict>

...

## Evolution

<How the idea moved. One line per round: premise vN → vN+1 and what changed and why.
This is the persisted record of the forging — re-forging next round diffs against it.>

- **v0 → v1**: <what was pruned, what was reshaped, which finding drove it.>
- **v1 → v2**: ...

## Viable variants

<Reframes that survive the pruning, ranked "most alive" first — grounded options, not
one radical pivot. Each names what it keeps, what it drops, why it survives the finding
that pruned the original, and one concrete next step to validate it. Include wedges
surfaced from incumbent holes. Mark each analyst-confirmed vs inference-only.>

1. **<Variant name>** — <keeps / drops / why it survives / first validation step.>

## Dead ends

<The pruned-branch ledger. Each: the claim, why it's dead (false / irrelevant /
already-owned), and the finding that killed it — so it is not revisited next round.>

## Expansion (parked)

<The scope stripped off during reduction to the kernel. Not deleted — parked here to
test later if the kernel proves out.>

## Caveats

<Where figures are approximate, which branches were inference vs verified, what could
not be confirmed and why. The report's value depends on the reader trusting its limits.>
```

---

## Verdict vocabulary

Per-branch:

- **VIABLE** — holds up against the strongest attack the agent could mount.
- **ADAPT** — the broad claim doesn't hold, but a reshaped version does; the finding
  tells the idea how to change (grounded, incremental).
- **PRUNE** — falsified, or true-but-irrelevant, or owned by someone the idea-holder
  can't out-execute. A dead end; record it in the ledger and don't revisit.

Overall recommendation (forge recommends; the user decides the pipeline transition):

- **PROCEED** — the load-bearing branches are VIABLE; build the premise roughly as
  stated. (Recommend `decided: pursue`.)
- **EVOLVE** — the premise-as-stated is reshaped by the adaptations into a stronger
  version worth carrying into another round or into execution. The common, healthy
  outcome for a serious idea. (Recommend it stays `explored` and loops, or `park` if
  shelved.)
- **DROP** — nothing load-bearing survives and no variant is worth the hours.
  (Recommend `decided: kill` — but only the user writes it.)
