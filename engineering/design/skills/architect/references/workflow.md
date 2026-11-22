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
   (`architect.scope`), else the two-path rule in SKILL.md (Inputs the architect never guesses) applies. Put
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
   Full flow in `code-graphing.md`. → _verify:_ the current-state model **covers every
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
   override. Then run `../scripts/scaffold.py --slug <slug> --title "<Title>" --tier <tier>` and land the
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
   back in (fixed attack dimensions and a reviewer fan-out prompt: `adversarial-review.md`). → _verify:_ a reader can trace every design step to a requirement, and the validation pass
   names real new problems, not none.
3. **Log the decisions as you make them.** Verified-facts table; every decision as Decision → Why →
   Grounding; a "considered and set aside: do not re-propose without new information" table. This
   is the anti-re-litigation doc. → _verify:_ nothing in the proposal is unexplained here.
4. **Spec it into test-gated blocks, cut to the dialed depth.** Decompose top-down and stop at the
   **decomposition depth** set for the run — interfaces → modules → components → functions
   (`depth-dial.md`); if the depth or its scope was not given, follow the two-path rule in SKILL.md (Inputs the architect never guesses)
   (`../scripts/scaffold.py` enforces it) — never pick a rung silently. Record it in the spec's "Decomposition depth" and "Acceptance by rung" sections (lint E9).
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
   blur the two. Then run `../scripts/lint.py <dir> --tier <tier>` as the cross-artifact gate: it fails on unfilled
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
   and observe (`execution.md`). Running, deploying and observing is the `deploy` skill's job (`engineering/infra/devops`).
   → _verify:_ the spec names each criterion and signal, and no script, harness or dashboard exists
   in the package.
