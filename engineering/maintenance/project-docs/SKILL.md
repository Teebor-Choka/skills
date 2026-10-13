---
name: project-docs
description: >
  Give a project a standard, enforceable docs/ structure: an overview, an optional deep spec, and
  ADR decision records, plus an AGENTS.md pointer, with diagrams at the right levels. A project is
  any coherent unit of work, a code repo, a subproject, or an infra/research/strategy effort, not
  only a codebase. Use whenever someone wants to document a project or repo, set up or standardize
  its docs/, write or backfill an overview, an ADR, or a spec, make docs consistent across many
  projects, add an AGENTS.md pointer, or check that a project's docs conform. Catches phrasings like
  "document this project", "write the overview and ADRs", "standardize our docs", "add diagrams to
  the docs", "is this documented". It authors the content (delegating ADR and spec-test discipline
  to architect, prose under strict de-slop) and ships a validator to keep it conformant. Not for API
  docs generated from code, prose polishing alone (unslop, prose-craft), or designing a system that
  does not exist yet (architect).
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# project-docs

Give a project the same documentation skeleton every time, author its content, and ship the tooling
that keeps it conformant. Two halves, opposite in nature, kept apart on purpose:

- **Authoring** (judgment): explore the project and write the docs. Generative, needs a model.
- **Enforcement** (mechanical): guarantee the structure exists and conforms. Deterministic, a
  script wired to pre-commit and CI.

The shape both halves obey is in [`references/contract.md`](references/contract.md) — read it
first. It is the single source of truth: the tree, the frontmatter schema, the ADR structure, the
decisions index, the AGENTS.md pointer, and the mandatory diagram levels.

## What counts as a project

A project is a directory that is a coherent **unit of work** an agent executes against: most often a
code repository, but equally a subproject inside one, or a non-code effort (an infra deployment, a
research track, a strategy or offer workspace). If it is something an agent picks up, works in, and
hands back as a unit, it is a project and these docs apply. A directory too small to be a unit of
work on its own does not need its own docs; fold it into its parent.

## The split authoring model

One rule shapes the authoring: **generate from truth, keep the engine's discipline, write in a
plain voice.**

- **Describe what exists, don't propose.** `overview.md` and `spec.md` document a system that is
  already there. Explore the project first (delegate a broad read to subagents when it is large),
  then write from what you found, grounded in a code graph when the project is code (see
  [`references/diagrams.md`](references/diagrams.md)). This is the explore-then-describe path.
- **Borrow the architect skill's discipline for the rigorous parts.** The decision records follow
  architect's decision-log shape (context, the decision, consequences, the alternative set aside),
  and a `spec.md` carries architect's positive **and** adversarial tests. Use that craft; do not
  run architect's forward-design pipeline, which is for building something new, not recording what
  is built.
- **Write every doc's prose at the strictest de-slop depth and the tersest length budget.** Lead
  with the fact, cut filler and template shape, no em dashes. Apply the unslop skill where it is
  available. Terse is the default; expand only where a subsystem genuinely needs it.

## Workflow: document a project

1. **Explore.** Map it: purpose, layout, stack or structure, how it builds/runs/deploys (if it
   does), the real decisions with their rationale. Prefer a code-graph tool over a blind file sweep
   for a code project. Fan the read out to subagents for a large or multi-part project.
2. **Decide the spec.** Apply the opt-in test in the contract. If you skip `spec.md`, record the
   one-line reason in `overview.md`.
3. **Write `overview.md`.** Purpose, a layout table, the stack or structure, how to build/run/deploy
   if applicable, and pointers to decisions and any deeper docs. Add the mandatory context or
   component diagram, seeded from the code graph for a code project (see `diagrams.md`).
4. **Write `spec.md`** when the opt-in test says so: the subsystems, each with its decisions and the
   tests that verify it (positive and adversarial), with a diagram per subsystem.
5. **Write the ADRs.** One `decisions/<slug>.md` per real decision in architect's shape, and the
   `decisions/README.md` index listing them. Record the set-aside alternative every time.
6. **Wire `AGENTS.md`.** Create or update the root `AGENTS.md` to point at `docs/overview.md` and
   `docs/decisions/`, plus the few build/run essentials. It points; it does not restate.
7. **Validate.** Run `python3 scripts/validate_docs.py <project>` and fix every finding before
   reporting done. For the exact flow and templates see [`references/flow.md`](references/flow.md).

## Diagrams

Mermaid, in-file, so they version with the prose. Mandatory levels are in the contract (a context
or component view in `overview.md`; a subsystem view per `spec.md`). Which **form** fits which shape
(flowchart, sequence, state machine, dependency DAG), how to seed the component view from a code
graph, and the boundary against code-level graphs (which stay a separate generated track, not
authored here) are in [`references/diagrams.md`](references/diagrams.md).

## Enforcement

The validator checks structure, never content. Run it standalone
(`scripts/validate_docs.py <project>`), across many projects (`--all <root>`), and wire it into a
project so it runs on every commit. The wiring is Nix-aware (registers as a `nix flake check` when
the project has a flake) and pre-commit-origin-aware (detects whether it uses plain `core.hooksPath`
hooks, the pre-commit framework, or Nix-managed git hooks, and joins that mechanism instead of
clobbering it). Procedure and `scripts/install_hook.sh` are in
[`references/enforcement.md`](references/enforcement.md).

## Scope

- Does: the project-level docs tree, its content, its diagrams, the AGENTS.md pointer, the validator.
- Does not: generate API or reference docs from code (that is a generated, linked track); polish
  prose as an end in itself (unslop, prose-craft); design a system that does not exist yet
  (architect). A project can need this skill and one of those; they compose.
