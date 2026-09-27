# The document set: purpose, required sections, skeletons

One section per artifact. Each gives its **purpose**, the **sections it must carry**, and a terse
**skeleton**, illustrated by a running example, an offsite DB-replication design. That example is
**illustrative and non-normative**: it is one domain (Kubernetes + Postgres) picked to make the
artifacts concrete. Substitute your own; never carry its stack into an unrelated design.

Don't hand-write the skeletons: run `scripts/scaffold.py --slug <slug> --title "<Title>"` to
generate the directory with every artifact's headings and `FILL-IN` markers, then
`scripts/lint.py <dir>` to check completeness before dispatch. The standards each artifact maps to
(EARS, RFC 2119, MADR, Gherkin, arc42, C4, Kahn) are in `methodology.md`; the architecture-style
catalog for the proposal's "design it twice" is in `architecture-styles.md`.

Naming: use a short slug for the effort (e.g. `db-replication`) as the prefix for the proposal and
spec. Everything cross-links by relative path so the directory is navigable on its own.

---

## 1. `research-notes.md`: grounded current state

**Purpose.** Establish what is _actually_ true today before proposing anything, so no later decision
rests on an assumption. This is written first and is the factual floor everything else stands on.

**Must carry:**

- Source line: exactly which repos/tickets/docs/web-searches were consulted, and when.
- Current architecture **grounded in the repo, not inferred**, each subsystem, with the file/module
  that proves it.
- An explicit split of **verified fact vs domain knowledge** (mark the "someone told me" numbers as
  such: they are real constraints with no policy behind them yet).
- **Greenfield vs existing**: call out what is a genuinely new capability vs an extension.
- Implications for the proposal (candidate hubs, shared primitives, scope that is net-new).

**Rule.** Research, don't recall: web-search current tools/versions, verify against official docs,
and cite each source (URL / repo path). Never infer state from an absent log line, empty grep, or
missing artifact. Confirm the thing _could_ have been observed, then assert it. Flag anything you
could not verify.

---

## 2. `README.md`: START HERE

**Purpose.** The entry point that lets any fresh session take over with zero information loss.

**Skeleton:**

```
# <Title> (<TICKET>): START HERE
<one paragraph: what this is, additive-to-what, what it is NOT>
## Read in this order   → numbered list of every artifact + its one-line job
## Status              → "Structurally complete, NOT finalized" + the open items to close
## The one decision the whole thing hinges on  → the single gate/measurement, stated plainly
## Environments        → pilot env, load-sim env, non-pilot env for destructive controls
## Visual artifacts    → published links (read-only)
## Repos referenced    → paths + git conventions to follow
```

---

## 3. `<slug>-proposal.md`: what & why

**Purpose.** The _what_ and _why_. Establishes intent and the design, at the level a reader needs to
agree with the direction before any _how_.

**Section order (numbered):**

1. **Purpose and non-goals**, and three things this is explicitly _not_.
2. **Where this plugs in today**: the deployment as it exists on `origin/main` right now.
3. **Requirements**: treated as _fixed constraints on the design that follows_, not open choices.
   Write each as an EARS sentence carrying an RFC 2119 keyword and give it an id (REQ-1, REQ-2); see
   `methodology.md`. This makes the tests derivable: every MUST becomes a positive test row, every
   MUST NOT an adversarial one.
4. **Design**: before committing, sketch **two or more structurally distinct candidates**, screen
   them against the structural red flags (principles §9), and synthesize the strongest. Present the
   result as numbered steps where **each is a consequence of the one before** ("read in order").
   Include a **Considered and set aside** paragraph inline where a strong alternative was rejected,
   stated fairly.
5. **Data model / history**, **6. Tenancy/access**, **7. Technology & licensing** (a full table:
   technology · role · license · status), **8. Deployment targets** (target · effort · reasoning).
6. **Risks & technical debt** (arc42 §11): the risks the chosen direction carries and the debt
   taken on knowingly. This is the section teams most often skip; do not.
7. **Open items and follow-up**: split _sizing/validation the pilot must produce_ from _out-of-scope
   but committed later, gated at a specific phase_.
8. **Rollout**: numbered phases, each with its own gate.
9. **Validation pass**, a self-adversarial section: "what did this design change open up?" Name the
   new problems the chosen direction introduces and show each is fixed in the design above (or
   tracked in open items). A validation pass that finds nothing is a red flag.
10. **Unresolved questions**: what is still open and who decides (RFC-style).
11. **Sources**: every external claim numbered and linked; mark any you could not fetch rather than
    silently asserting it.

---

## 4. `decision-log.md`: the anti-re-litigation doc

**Purpose.** Capture every load-bearing decision, its rationale, and its grounding so a fresh agent
never re-derives or re-argues anything.

**Must carry:**

- **Verified facts** table: `Fact | How verified | Consequence`. These are checked, not assumed; if
  one is later contradicted, revisit the decision resting on it.
- **Decisions in the order made**: each as a MADR record (see `methodology.md`) with **Decision →
  Status → Why → Grounding → Confirmation** (D1, D2, …). Status is one of Proposed / Accepted /
  Deprecated / Superseded (a superseded one points to its replacement and keeps its reasoning).
  Confirmation names the harness check or fitness function that would fail if the decision were
  violated. Where a decision corrects an earlier premise, say so.
- **Considered and set aside** table: `Option | Why set aside`, headed "do not re-propose without
  new information".
- **Open items**: the spec is NOT finalized until these close; give each a concrete close condition.

---

## 5. `<slug>-spec.md`: how, to ticket granularity

**Purpose.** The _how_, block by block, detailed enough that each block becomes a ticket.

**Must carry:**

- A short preamble that may include **Design amendments**, grounded deviations from the proposal
  discovered while verifying the deployment; they supersede the proposal, and the superseded
  reasoning is left in the proposal for the record.
- **Block index** table: `# | Block | Runs on | Depends on | Satisfies | version/capability gate`.
  The **Satisfies** column back-links each block to the requirement id(s) (REQ-n) it delivers, so no
  block exists that no requirement asked for and no requirement ships without a block
  (`methodology.md`). `scripts/lint.py` warns on a missing backlink and checks that these
  dependencies match the development graph's edges.
- **Block 0: Preconditions** grouped first (e.g. 0a/0b/0c), then blocks numbered **in execution
  order**.
- **Each block, specified identically:** Purpose · Architecture · Interfaces (Input / Output /
  **Config surface**) · **Verification tests** table · **Adversarial tests** table · (where it
  declares a capability) a **capability check** table (`Cimg` present-in-image, `Crun` active-at-
  runtime). A block is "done" only when both test classes pass. Derive each block's **Output**
  contract from what its downstream consumers actually need (consumer-first), not from its internals.
- **Escalation appendix**: off-the-shelf tools, each matched to a _different_ shortfall, with a
  `Tool | License | Adds | Cost | Reach for it when` table. **Never hand-build a pipeline.**
- **Acceptance criteria**, the end-to-end gate: what must hold, including the hinge measurement and
  the numbers reserved to be produced by the pilot.

Test-table shape (both classes use it):

```
| Test | Setup / Inject | Expected result |
```

---

## 6. `development-graph.md`: the build DAG

**Purpose.** The spec's blocks as a build DAG for a fleet of agents.

Produce it by **planning the spec's blocks as work for the agents**: eliminate/parallelize/sequence/
loop them into an execution graph (node table, mermaid DAG, waves table, loop register, elimination
log, concurrency cap). The interface: the spec's blocks go in; an execution DAG whose edges match the
block-index dependencies exactly comes out.

The graph MUST be acyclic. Waves are the Kahn levels (each runs in parallel); the **critical path**
is the longest dependency chain and sets the irreducible wall-clock time, so annotate it, adding
agents past its width is wasted (`methodology.md`). `scripts/lint.py` topologically sorts the graph
(a cycle is a hard fail) and checks its edges against the spec's block table.

---

## 7. `agent-methodology.md`: how a fleet executes

**Purpose.** How agents pick up and run the DAG.

**Must carry:** one block ↔ one agent; an agent reads **only** its brief + the referenced spec block

- `invariants.md`, never session history; same-wave agents start from the same `origin` baseline; an
  agent starts only when all its entry blocks are GREEN. Plus: parallelism/serialization + **merge
  queue** (serialize merges, rebase in dependency order, shared-file/restructuring edits are serial);
  **spec/test/build isolation** (the agent that authors a block's tests sees only the spec block, never
  the implementation or the coder's reasoning, and adversarial tests are authored independently of the
  positive ones, a hard boundary against the test echo chamber); **capability checks** (`Cimg`/`Crun`,
  verified by observation never inferred from absence); the **definition of GREEN** (both test classes
  pass + interface contract stable); **environments** (pilot / load-sim / non-pilot for destructive
  controls); inherited engineering guardrails (reproduce at smallest boundary, assert the bad
  behaviour, prove the change is in the component under test, preserve design semantics).

**`invariants.md` (the constitution).** A package-level file of rules (INV-1, INV-2, …) that MUST
hold across every block: data-safety guarantees, ordering constraints, security boundaries. Every
per-node brief carries these verbatim, not by reference, because information is lost across handoffs
and constraints are stripped first. This is the single strongest defense against multi-hop context
loss.

---

## 8. `test-methodology.md`: how "done" is proven

**Purpose.** The shared contract behind every block's test tables.

**Must carry:**

- **Two classes per block**: verification (did we build the thing) and adversarial (does it survive
  the world). Every case that can fail in two directions gets both signs.
- **Capability checks**: `Cimg` (present in image, static scan) and `Crun` (active at runtime,
  queried on the running system). Never infer state from an absent signal.
- **Authoring rules**: both signs per case; **assert the bad behaviour explicitly**; name the
  fault-injection point; destructive negative controls run in a non-pilot env.
- **Fault-injection catalogue**: a `Block | Inject | Must observe` table covering every block.
- **Acceptance gate**: the integration criteria, including the hinge measurement, with its exact
  pass/fail if known (and flagged as OPEN if not yet defined; an undefined gate is a judgment call,
  not a gate).

---

## 9. `agent-plans/block-*.md`: one brief per DAG node

**Purpose.** A self-contained execution brief so an agent needs only the brief + its spec block.

**Skeleton (every brief identical):**

```
# Block <n>: <name> (agent brief)
**Track:** … · **Wave:** … · **Spec:** `<slug>-spec.md` § Block <n>
**Depends on (entry):** <blocks that must be GREEN>
**Unblocks:** <downstream blocks>
**Satisfies:** <REQ-n it delivers> · **Inherited invariants:** <copy the relevant INV-n from `invariants.md`>
## Objective        → one paragraph
## Build            → concrete steps
## Interface (contract)  → Output that downstream blocks rely on; config surface
## Verification tests    → table
## Adversarial tests     → table
## Definition of done (GREEN)  → checklist; done only when fully checked
```

Add an `agent-plans/README.md`: the wave/order table + how to use a brief + "if brief and spec
disagree, the spec wins, and fix the brief".

---

## 10. Visual artifacts

See `deliverable-formats.md`: the mermaid DAG (mandatory, lives in `development-graph.md`) and the
optional branded, self-contained HTML rendering of the proposal.
