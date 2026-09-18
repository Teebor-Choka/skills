# Auditing an existing skill set

Three lenses for raising a set of skills (and the always-on instruction file — `CLAUDE.md` /
`AGENTS.md` — and any hooks) to standard. Each is an audit, not an edit: **present findings and
get approval before changing anything.** Show the work as the tables below so the operator can
see every proposed change and reject any of them.

Run them in any order; they compose. Do one lens across the whole set, present, apply the
approved subset, then the next lens.

## Lens 1 — standards over rules

Find every rule — "never do X" / "always do Y" — in `CLAUDE.md`, every skill, and every hook.
For each, name the **standard behind it** (the outcome it was protecting) and rewrite the rule
as that standard, so the agent can apply judgment instead of matching a literal command. Leave
a rule hard only when it is a **real boundary**: something not to touch, a safety/legal limit,
or an external contract. Also flag any two rules that **contradict** each other.

Present:

| Rule as written                          | Standard behind it                   | Rewrite (or "keep — boundary")                                                   |
| ---------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------- |
| never write comments                     | comments should not restate the code | match the surrounding file's comment density and style                           |
| always run the full suite before pushing | don't push a regression              | run the tests that cover the change; run the full suite when the change is broad |
| never edit `vendor/`                     | vendored code is externally owned    | keep — boundary                                                                  |

Add a short "contradictions" list beneath the table. Change nothing until approved.

## Lens 2 — interface, not example

Find every skill that hands the agent an **example output to copy**. Classify each:

- **Factory-worker** — output must match a fixed format every time. Leave it alone; the example
  is doing its job.
- **Creative** — output should fit the situation. Rewrite the skill as an **interface**: what is
  needed, what the constraints are, what "done" looks like — with no single example to imitate,
  so runs stop converging on the one sample.

Present your call and the reason before changing anything:

| Skill          | Factory or creative | Why                                    | Proposed change                                                                         |
| -------------- | ------------------- | -------------------------------------- | --------------------------------------------------------------------------------------- |
| commit-message | factory             | every commit must match the same shape | keep example                                                                            |
| design-review  | creative            | good reviews differ per design         | replace the sample review with an interface: goals, constraints, what "done" looks like |

## Lens 3 — move context to reference files

Find every block of context that loads on **every session or every skill run** but only matters
for **one kind of task**. Move each into a reference file next to the skill that uses it, and
leave a one-line pointer that says _when to load it_. The goal: a `CLAUDE.md` that routes, and
skills that stay lightweight with the heavy context in references (progressive disclosure, see
`authoring.md`). **Do not cut any context** — every block either stays where it is or moves to a
reference file.

Present a before/after file tree and every pointer you would add, before moving anything:

```
before                          after
CLAUDE.md  (420 lines)          CLAUDE.md  (90 lines, routes)
                                references/python-conventions.md   ← "load when editing Python"
                                references/deploy-runbook.md        ← "load when deploying"
```

## The approval gate

For all three lenses: audit read-only, present the table(s)/tree, and wait. Apply only what the
operator approves, then re-run the skill validators (`scripts/validate_skill.py`, and the repo's
own checks) and re-format. Nothing ships on the auditor's say-so alone.
