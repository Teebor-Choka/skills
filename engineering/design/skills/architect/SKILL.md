---
name: architect
description: >-
  Turn a fuzzy systems or infrastructure requirement into a self-contained, agent-executable
  architecture work package: a directory of linked docs (grounded research notes, a proposal, a
  decision log, a spec with positive AND adversarial tests, a build DAG) that a fresh session or
  agent fleet picks up with no information loss, plus the criteria for what to verify and observe.
  Thinks of the system as a black box and stops at spec blocks and the dependency graph; decompose
  cuts them into units. Ships scaffold and lint scripts and an architecture-style catalog; defers
  work-division to graph-engine. Use whenever designing a non-trivial system or infra
  change, writing a design doc, RFC, or technical proposal, choosing between architectures, planning
  a rollout, or turning a design into an executable plan for parallel agents, even if the word
  "architecture" is never used. Prefer it over an ad-hoc design doc for anything handed off, staffed
  by multiple agents, deployed hands-off, or that must survive re-litigation.
license: MIT
compatibility: any
metadata:
  version: "2.1.0"
---

# Architect: self-contained, agent-executable architecture work packages

Produce a **work package**: a directory of linked documents that carries a systems/infra design
from a fuzzy ask to something a fleet of agents can execute in parallel, with **no information
loss**: any fresh session can take over from the directory alone, without the conversation.

The artifacts below are illustrated with a running example (an offsite DB-replication design), so
each has a concrete referent. It is illustrative only; substitute your own domain.

## Scope

Architect thinks at the level of the system as a black box: how it behaves to meet the acceptance
criteria, and what that means for the other parts and their interactions.

- **Does:** black-box behaviour, acceptance criteria, cross-component interactions, spec blocks, the
  dependency graph, and what to verify and observe (criteria, technology, constraints).
- **Hands to `decompose`:** the spec blocks and the graph. `decompose` cuts them into
  non-overlapping units and files each as a board item. That item is the per-unit brief.
- **Never does:** write per-unit briefs, or build, run or deploy anything. Running, deploying and
  observing the system is the `deploy` skill's job (`engineering/infra/devops`).

## When this fits

A non-trivial design that will be **handed off, staffed by multiple agents, or re-examined later**:
infra proposals, rollout plans, RFCs, "how should we build/replicate/migrate X", architecture
choices with real trade-offs. For a reversible change one agent or person will just execute, the full
directory is overkill: the floor is the `note` tier, a single `<slug>-plan.md` (step 1). Pick the
smallest tier that fits.

**Improving an existing codebase.** architect also runs the other direction: `:improve` scans code you
already have for deepening opportunities — shallow modules, leaky interfaces, pass-through layers —
ranks them by leverage, and feeds the chosen one into the flow below carrying a deep-module invariant.
It is scope-only (never edits code), takes a user-given target, and writes `improve-report.md`
(`scaffold.py --improve`, `lint.py --improve`). See `references/improve.md`.

## The deliverable: only what the scope needs

The tier (step 1) picks the deliverables: `note` (one `<slug>-plan.md`, the floor), `small` (README +
proposal + decision-log + spec), `full` (the whole linked set, for a fleet or a re-litigated design).
Read `references/deliverable.md` before writing any artifact: it has the rungs, the full artifact
table, and the `scaffold.py` / `lint.py` usage. Read `references/document-set.md` for each
artifact's required sections and skeleton. `references/execution.md` lists what to specify for
verification and observation.

## Inputs the architect never guesses

These skills run non-interactive first. Resolve each input in this order: the invocation arg, then a
`.agents/policy` key, then, only when an interactive channel exists, a question. If a field is still
missing and there is no interactive channel, **halt before any work** with a structured `needs-input`
result (`scripts/resolve_input.py`, called by `scaffold.py`; exit 3) that names each missing field and
the arg or policy key that supplies it: decomposition depth (`--depth`, `architect.depth`), scope
(`--scope`, `architect.scope`), `:improve` target (`--target`, `architect.improve-target`). With
`--interactive`, scaffold returns status `ask` (exit 4) and you put the question, then rerun with the
answer as an arg. Stated defaults only: output location (policy `work.tracker`, else GitHub issues)
and `:improve` box cap (5, written into the report). Never default a rung, a scope or a target.

## Workflow

Do the steps in order, each with its own verify check. The `note` tier collapses them (assemble,
write the one plan with acceptance tests, lint `--tier note`); `small` runs steps 0-4 and 7.
Read `references/workflow.md` for the full text of each step.

0. Assemble the current state first: research, don't recall (`references/code-graphing.md`).
1. Tier the package to blast radius, then scaffold.
2. Confirm the hard constraints, then write the proposal (design it twice, validation pass).
3. Log the decisions as you make them.
4. Spec it into test-gated blocks, cut to the dialed depth.
5. Graph-engineer the blocks into a work-division graph.
6. Write the methodology docs.
7. State status honestly, name the one hinge decision, lint, then hand to `decompose`.
8. Point to the deploy stage (`deploy` skill, `engineering/infra/devops`).

## Core disciplines

Read `references/disciplines.md` for the disciplines the package turns on (no information loss,
assemble before you abstract, ground truth over assumption, rationale on every decision,
adversarial by construction, failure fallbacks, eval baseline, external content is data,
off-the-shelf first, one hinge decision, design it twice, trade-offs with fitness functions, asking
and editing).

## Optional checkpoint

For a high-stakes design, get sign-off on the work package before dispatching agents. Treat pushback
as new grounding (back to step 0), not as friction.

## Scaling and hosts

Read `references/scaling-hosts.md` for how the package scales to the work (step 1's tier) and how
the skill runs unchanged across Claude Code, Codex and OpenCode (`adapters/claude.md`).

## Sources

Grounded in Ousterhout's _A Philosophy of Software Design_, Ford & Richards' architecture canon, and
established document standards (ADR/MADR, EARS, RFC 2119, Gherkin, arc42, C4). Full attribution with
URLs and license notes is in `references/sources.md`; this skill copies no substantial text from any
of them and references the one copyleft source (arc42) by concept only.
