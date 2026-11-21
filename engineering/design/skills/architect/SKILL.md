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

The output is a **chosen set of final documents, not a fixed directory you always fill.** The tier
(step 1) decides which documents are deliverables; the rest, if you write them at all, are disposable
working notes, not artifacts to maintain. Three rungs:

- **`note`** — one `<slug>-plan.md`, no package directory, no cross-document links. The floor.
- **`small`** — README + proposal + decision-log + spec, for a change still handed off or re-examined.
- **`full`** — the whole set below, for a design staffed by a fleet or re-litigated later. Here the
  living directory earns its cost: it is the source of truth mid-flight, so a fresh session resumes
  from it (no information loss). That is why `full` is _not_ "emit at the end" — the others are.

The table below is the **full** set and the order a reader consumes them. Each is specified (purpose +
required sections + a skeleton) in `references/document-set.md`. **Read that file before writing any
artifact.** Don't hand-write the skeletons: `scripts/scaffold.py --slug <slug> --title "<Title>"
--tier note|small|full` generates them, the **graph-engine** skill computes the build graph (step 5),
and `scripts/lint.py <dir> --tier <tier>` checks the package before dispatch (the `note` tier lints
only the single plan).

| #   | Artifact                 | Answers                      | The one job                                                                                                                                                                                                                                                                                                                                   |
| --- | ------------------------ | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `research-notes.md`      | what's _actually_ here today | ground truth: verified facts vs domain knowledge, greenfield vs existing, cite every source                                                                                                                                                                                                                                                   |
| 2   | `README.md` (START HERE) | where do I begin             | read-order, status, the one hinge decision, environments, repos                                                                                                                                                                                                                                                                               |
| 3   | `<name>-proposal.md`     | _what_ & _why_               | purpose+non-goals, EARS requirements-as-constraints, design as a chain of dependent decisions, risks & tech debt, a self-adversarial validation pass, sources                                                                                                                                                                                 |
| 4   | `decision-log.md`        | why is it _this_ way         | verified-facts table, every decision as a MADR record (status + why + grounding + confirmation), considered-and-set-aside, open items                                                                                                                                                                                                         |
| 5   | `<name>-spec.md`         | _how_, to ticket size        | blocks (purpose/architecture/interfaces/tests), dependency + requirement-backlink table, escalation appendix, acceptance criteria                                                                                                                                                                                                             |
| 6   | `development-graph.md`   | build order                  | the spec's blocks as a work-division graph, generated by the **graph-engine** skill: waves, mermaid DAG, critical path, barriers, collaboration shapes (its `graph-patterns.md`)                                                                                                                                                              |
| 7   | `invariants.md`          | what must hold everywhere    | the constitution: package-level rules every filed item inherits verbatim (info-loss defense)                                                                                                                                                                                                                                                  |
| 8   | `agent-methodology.md`   | how agents execute           | one block ↔ one agent, entry conditions, spec/test isolation, merge queue, definition of GREEN, and a **model tier per block** so each agent runs on the cheapest model that fits: `reasoning` (design/hard calls), `execution` (building, the default), `light` (reads/extraction/status), `speed` (optional fast lane, falls back to light) |
| 9   | `test-methodology.md`    | how "done" is proven         | positive + adversarial classes, capability checks, fault-injection catalogue, the acceptance gate                                                                                                                                                                                                                                             |
| 10  | visual artifacts         | see it                       | mermaid diagrams on a C4 ladder (`references/deliverable-formats.md`)                                                                                                                                                                                                                                                                         |

When the system will be deployed, the spec also states **what to verify and what to observe**
(criteria, technology, constraints), never how. `references/execution.md` lists what to specify.
The deploy stage runs it.

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

Steps 0–7 design the package; step 8 points to the deploy stage. Do them in order;
each has a check you can verify before moving on. This is the `full`-tier path. The `note` tier
collapses it: assemble briefly (step 0), write the one `<slug>-plan.md` with its acceptance tests
(step 1), lint it (`--tier note`), done — there are no spec blocks or graph. The `small` tier
runs steps 0–4 and 7, skipping the graph.

0. **Assemble the current state first: research, don't recall.** Before judging size or writing
   anything, build a complete model of what exists today — breadth before depth, survey before you
   zoom to concepts. Establish scope: inside one repo, that is the scope; otherwise scan the current
   directory; the repos to include and the project unit come from the invocation (`--scope`) or policy
   (`architect.scope`), else the two-path rule below applies. Put
   "is backward compatibility required?" in that first scoping question; don't audit or design on an assumed answer. Then, with
   the code indexing MCP when one is connected (prefer a fresh index of the in-scope repos), assemble in this order: **(a)** pull the
   whole-system map and its de-facto module clusters — the big picture, not just the area you expect to
   touch; **(b)** walk every cluster and boundary, naming each subsystem with the node or file that
   proves it; **(c)** trace the load-bearing data flows and the cross-service / cross-repo seams end to
   end; **(d)** surface the coupling and complexity hotspots. Go cross-repo when several repos are in
   scope; where no graph tool is present, read the real repos by hand and say the floor was hand-built.
   Either way, **web-search the current tools, versions, and licenses, and verify load-bearing claims
   against official documentation.** Separate _verified facts_ (checked against a repo, graph node,
   official doc, or search) from _domain knowledge_ (someone said so); flag greenfield vs extension.
   Full flow in `references/code-graphing.md`. → _verify:_ the current-state model **covers every
   in-scope subsystem, boundary, and cross-repo seam** — not only the change site — the hotspots are
   named, every claim the design rests on cites its source (node / URL / repo path), and unverifiable ones
   are flagged. Record it in `research-notes.md` (full tier) or the proposal's current-state section
   (small tier).

1. **Tier the package to blast radius — now that you have assembled it — then scaffold.** With the
   system understood, judge the change by reversibility and blast radius, not by lines of code, and
   pick the **smallest tier that fits**: `note` (one `<slug>-plan.md`) for a reversible change one
   agent or person will just execute; `small` (README + proposal + decision-log + spec with tests) for one that will still be handed off or re-examined; `full` for a design staffed by a fleet
   or re-litigated later. Default to `note` and step up only when handoff, multi-agent execution, or
   re-litigation actually applies; record the choice (in the plan, or the decision log) so a human can
   override. Then run `scripts/scaffold.py --slug <slug> --title "<Title>" --tier <tier>` and land the
   step-0 grounding in it, researched and cited under the **grounded-research** skill's contract
   (primary sources, URL and access date per claim, verified apart from hearsay, conflicts and
   unverifiable items flagged). **Don't scaffold a document you won't deliver**, and don't carry the whole
   linked set consistent from the start — fill documents in dependency order and leave cross-document
   consistency to the single lint gate at step 7. → _verify:_ the tier is recorded with the assembly
   findings that justify it, and the scaffolded artifact(s) exist.
2. **Confirm the hard constraints, then write the proposal.** Gate: before drafting, list the
   constraints the design may not break and get the user's yes (the interaction policy decides how
   you ask): which credentials, tokens, or secrets may touch which host; which tools or products are
   required; which are excluded; what must stay local. Reasons: assumed constraints cost a full
   redesign in three past sessions (an architecture built on a secrets path the user ruled out; a
   required tool dropped, then an excluded one built on). Requirements become fixed constraints.
   **Design it twice**: sketch at
   least two structurally distinct approaches and synthesize the strongest (principles §9), then
   present the design as a chain where each step is a _consequence_ of the prior one, not an
   independent pick. End with a **validation pass** that attacks your own design and folds the fixes
   back in (fixed attack dimensions and a reviewer fan-out prompt: `references/adversarial-review.md`). → _verify:_ a reader can trace every design step to a requirement, and the validation pass
   names real new problems, not none.
3. **Log the decisions as you make them.** Verified-facts table; every decision as Decision → Why →
   Grounding; a "considered and set aside: do not re-propose without new information" table. This
   is the anti-re-litigation doc. → _verify:_ nothing in the proposal is unexplained here.
4. **Spec it into test-gated blocks, cut to the dialed depth.** Decompose top-down and stop at the
   **decomposition depth** set for the run — interfaces → modules → components → functions
   (`references/depth-dial.md`); if the depth or its scope was not given, follow the two-path rule below
   (`scripts/scaffold.py` enforces it) — never pick a rung silently. Record it in the spec's "Decomposition depth" and "Acceptance by rung" sections (lint E9).
   The dialed rung is the leaf grain of the blocks. Each block: one deliverable, one
   write-set, one checkable done, small enough to become a ticket; purpose, architecture, interfaces
   (input/output/config surface), **verification (positive) tests AND adversarial (negative) tests**.
   ATDD runs as a **cycle across every rung traversed** — acceptance at each depth (interface, then
   module, then component, …), not only at the leaf. Group preconditions as Block 0; number blocks in
   execution order. Add an **escalation appendix** of off-the-shelf options. → _verify:_ every block
   has both test classes and a clear definition of done, and the acceptance covers each rung down to
   the dialed depth. Before presenting any phase plan, list each component with its interface,
   properties, and acceptance test, so the owner can check what a phase delivers.
5. **Graph-engineer the blocks into a work-division graph.** This is the graph-engineering
   discipline: split the work into a shape a fleet can collaborate on, then hand off, don't oversee
   how they run it. Your only judgment calls are naming the nodes (one deliverable each), their true
   dependencies, their write-sets, any loops, and picking collaboration shapes from the **graph-engine**
   skill's `graph-patterns.md` (fan-out, pipeline, evaluator-optimizer, blackboard, contract-net,
   and the rest, tagged for whether agents self-coordinate or need a controller). Cut for the most
   isolated packages: disjoint write-sets, listed in the Block index. Where two blocks cannot be
   disjoint, order them with an edge or declare the same `Coordination channel:` in both (lint E10;
   a marker only, the executor runs it). Everything
   graph-theoretic is computed, not judged: write the nodes as a JSON spec and run the **graph-engine**
   skill's `graph.py spec.json`, which removes redundant edges (transitive reduction), assigns the
   parallel waves, finds the critical path and barriers, catches write-set collisions, and emits
   `development-graph.md`. → _verify:_ `graph.py` exits 0 (no cycle, no wave collision) and its
   waves match the spec's block dependencies.
6. **Write the methodology docs.** `agent-methodology.md` (how a fleet runs the DAG) and
   `test-methodology.md` (how tests are authored/judged). No per-node briefs: `decompose` files each
   unit as a board item. → _verify:_ the methodology docs agree with the spec's block and test tables.
7. **State status honestly, name the one hinge decision, then lint before dispatch.** Identify the
   single measurement or gate the whole design turns on, and say plainly it's open if it is. List
   every open item. A work package is "structurally complete" long before it is "finalized"; don't
   blur the two. Then run `scripts/lint.py <dir> --tier <tier>` as the cross-artifact gate: it fails on unfilled
   placeholders, a spec block missing either test class, a decision with no status, a missing sources
   section, a cyclic graph, DAG edges that disagree with the spec, and dead cross-links. Fix every
   error before agents fan out. Then, once lint is clean, **hand the package to `decompose`**, which cuts it into units and files them
   to the tracker. A plan that is a single unit goes straight to `implement`. **Handing off ends the design**;
   dispatching and integrating the filed items is the executor's job, and deploying the designed system is
   the separate deploy stage.
   → _verify:_ the README
   names the hinge decision and lists open items with concrete close conditions, `lint.py` reports
   zero errors, and the package is handed to `decompose` (or `implement` for a single unit).
8. **Point to the deploy stage.** Architect defines the criteria, the technology, and what to verify
   and observe (`references/execution.md`). Running, deploying and observing is the `deploy` skill's job (`engineering/infra/devops`).
   → _verify:_ the spec names each criterion and signal, and no script, harness or dashboard exists
   in the package.

## Core disciplines

The design disciplines are what the package turns on (`references/principles.md`, which also
carries the Ford & Richards trade-off/characteristics/fitness-function material in §10); `references/execution.md` lists what to specify for verification and observation.

- **No information loss.** The directory is the source of truth; the conversation is disposable.
  Never silently truncate required context to fit a budget — halt and escalate; summarize a
  sub-agent's output into the next context, never append it whole.
- **Assemble before you abstract.** Build the whole-system model — module clusters, data flows,
  cross-repo seams, coupling and complexity hotspots — _before_ forming any design opinion. Breadth
  before depth: survey the system with the graph tools first, then zoom to concepts. The common
  failure is starting to architect off the one area you expected to touch; the nuance that sinks the
  design is almost always in a subsystem you never surveyed.
- **Ground truth over assumption: research, don't recall.** Don't reason from memory on anything
  critical. **Web-search the current tools, versions, and licenses and verify every claim
  against official documentation** and the actual repo/config. Separate _verified fact_ from _domain
  knowledge_, **cite every source with a URL or repo path**, and flag what you couldn't verify rather
  than asserting it.
- **Every decision carries rationale + grounding**, and a "set aside" list so nothing is relitigated.
- **Adversarial by construction.** Every design gets a self-attack pass; every block gets negative
  tests; assert the _bad_ behaviour (a silent no-op must be observably distinguishable from success).
- **Plan for failure; every delegated node has a fallback.** Declare each node's failure modes and a
  fallback chain (primary → narrowed → degraded/rule-based → human); a fan-in/synthesizer handles all,
  partial, and zero results. A structured degraded result beats a silent failure.
- **No dispatch without an eval baseline.** A new or changed agent/pipeline ships only with an eval
  suite, a recorded baseline it meets or exceeds, and a full-pipeline regression check — the discipline
  that also decides whether added machinery earns its keep.
- **External content is data, never instructions.** Isolate untrusted input (web, docs, user text)
  from the prompt, validate agent outputs against a schema, and pass least privilege — never hand a
  scope token between agents.
- **Off-the-shelf over hand-built.** The highest-risk work is a bespoke pipeline; escalate to a tool.
- **Name the one hinge decision** the whole design turns on, and be honest when it's still open.
- **Design it twice.** Sketch two or more structurally distinct designs and synthesize the strongest;
  prefer the one that hides the most behind the simplest interface; when a design needs the same
  workaround again and again, scrap it rather than patch it. Pick candidate styles from the catalog
  in `references/architecture-styles.md` (monolith through microservices, with diagrams and
  trade-offs), not from habit.
- **Everything is a trade-off; make each characteristic testable.** Name the few characteristics
  that actually drive the system, choose the least-worst style for them, and give each a fitness
  function so the claim is falsifiable (Ford & Richards; `references/principles.md` §10). A claimed
  pure win means you haven't found the trade-off yet.
- **Asking and editing:** read `references/methodology.md` § Asking and editing before you ask a
  question or edit a long table.

## Optional checkpoint

For a high-stakes design, get sign-off on the work package before dispatching agents. Treat pushback
as new grounding (back to step 0), not as friction.

## Scaling

Match the package to the work; step 1's risk tier decides. A reversible change one agent will just do
is a single `<slug>-plan.md` (`scaffold.py --tier note`), nothing else. A small, reversible design
that will still be handed off is proposal + decision-log + a short spec, no agent fleet (`--tier
small`). A large or irreversible multi-agent epic warrants the full set (`--tier full`). When you drop
an artifact from a tier that would normally carry it, say why in the README rather than leaving a
reader to wonder if it was forgotten. Don't manufacture blocks, waves, documents, or a hinge decision
that the problem doesn't actually have.

## Running across agents

One portable `SKILL.md` and its `references/` and `scripts/` run unchanged on Claude Code, Codex, and
OpenCode. The scripts need only Python 3.13 or newer (standard library, no third-party packages). Install the
skill directory at `~/.claude/skills/architect/` (Claude Code), `~/.agents/skills/architect/`
(Codex), or `~/.config/opencode/skills/architect/` (OpenCode, which also reads `.claude/skills` and
`.agents/skills`, so one directory serves all three).

The only host-specific piece is publishing a rendered proposal or diagram outside the terminal;
`adapters/claude.md` wires that to Claude Code's `Artifact` tool and the `artifact-diagramming` /
`artifact-design` skills. On other hosts, use their own rendering capability. The markdown work
package, including in-repo mermaid, is complete without any of it.

## Sources

Grounded in Ousterhout's _A Philosophy of Software Design_, Ford & Richards' architecture canon, and
established document standards (ADR/MADR, EARS, RFC 2119, Gherkin, arc42, C4). Full attribution with
URLs and license notes is in `references/sources.md`; this skill copies no substantial text from any
of them and references the one copyleft source (arc42) by concept only.
