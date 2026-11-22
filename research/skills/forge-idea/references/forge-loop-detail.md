Paths in this file are relative to the skill directory.

## Step 1. Interrogate and reduce to the kernel

Do **not** just restate the premise and ask for a nod. Ask one question at a time or in batches,
if relevant together, wait for the answer, push back on every soft one, and don't synthesize the
kernel until the answers line
up — pose the questions through a decision dialog where the host offers one. The exception is
open-ended brainstorming: when the user is exploring rather than deciding, let them drive with
their own questions instead of firing a dialog every turn. Interrogate until it is sharp:

- **Target** — who or what is this _for_? Name it explicitly. (Not necessarily a
  paying buyer — the idea may be a research bet or an internal tool; but the target
  must be named.)
- **Why / mechanism** — _why_ does this actually work? What has to be true for the
  value to exist at all? The Why must come out of the interrogation.
- **Success metric** — what observable outcome would prove it worked?
- **Riskiest belief** — which single assumption, if wrong, collapses everything?
- **Hidden assumptions** — what is taken for granted about demand, cost, timing, or
  capability?
- **Fit criteria (the worth-it bar)** — _conditional: only when the idea is being
  pursued for a target that already has a strategy, mandate, or constraint set._ Name
  the criteria that make an idea worth _this_ holder's time and capital: their
  validation bar, unit economics, capability/scale limits, timing window, and what
  they deliberately refuse to build. An idea can be fully viable in the world yet not
  worth pursuing for _this_ holder — capturing these criteria now is what lets step 5
  score strategic fit. If no such target exists (an open-ended bet), skip it; fit then
  degrades to a caveat rather than a scored dimension.

Then **reduce to the kernel**: the single sharpest, minimal, falsifiable form of the
idea, the smallest claim that, if it survives, keeps the idea alive. The kernel is
what localizes the research: a broad premise gives the agents no coordinates and they
return a generic landscape; a sharp kernel gives them a specific target they can
falsify. Reduction is **focus, not amputation** — the scope you strip off is **parked**
as an `## Expansion (parked)` note in the file, never deleted. Nothing is cut without
evidence; the kernel is only what you test _first_.

- **Interactive mode** (user is present): multi-turn grill, iterate on the kernel
  until it holds up.
- **Async / remote mode** (fired without the user at the keyboard): infer the kernel
  from the note, state it as a single sentence, and **stop at the confirm-the-kernel
  gate** — present the one-line kernel and wait for a thumbs-up or correction before
  spending any tokens on the fan-out. Cheap to confirm, expensive to aim wrong.

## Step 4. Fan out the stress-test squad

Spawn one agent per branch **concurrently and independently** — launch them together,
not one after another, and they must not see each other's work; independent convergence
is the signal. Each agent attacks its branch hard **and reports constructively**,
returning the structured verdict in `references/forge-verdict.schema.json`:

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

**Engine scales by rigor.** Default: fan out general research subagents that
web-research and can run their own scoped research pass. For a deep "be thorough" run,
drive a deterministic find → adapt → prune → re-test loop with the verdict schema as each
agent's structured output. Bind these stages to your agent's real mechanism (parallel
subagents, multiple headless processes, or a workflow engine) as laid out per agent in
`references/cross-agent.md`.

**Cost guardrail.** Watch the double fan-out (grounding research pass + per-branch
agents each possibly running their own research pass):

- _Gut-check:_ 1 branch, 1 round, **no** nested research pass.
- _Thorough:_ 5–6 branches, orchestrated loop, nested research allowed.
  The confirm-the-kernel gate exists so a mis-aimed kernel never burns a full fan-out.
  Match fan-out width to the kernel's load-bearing claim count — extra agents add cost and
  redundant findings, not coverage. Split one agent across a single claim only when that
  claim genuinely has two independent attack angles. `references/cross-agent.md` covers
  per-agent parallelism limits.

## Step 5. Prune and reshape

Cut PRUNE branches without mercy, and record them in the dead-ends ledger so they aren't
revisited. Apply the ADAPT adaptations and fold in the opportunity signals. But **do
not lurch**: keep the reshaping **grounded and incremental**, and present **several
grounded options** for where the idea could go rather than one radical pivot. Note
where agents converged (high confidence) and where they split (the split is itself a
finding — surface it, don't average it). The reshaping proposes; the smith checkpoint
decides which option to converge on.

**Then diverge — generate the out-of-the-box variants.** Incremental reshaping keeps the
primary premise honest, but the highest-value output is often a reframe the literal idea
never named. Beyond the grounded reshaping, generate **2–4 non-obvious variants anchored to
the holder's actual assets and target** — an adjacent wedge, a different buyer, the B2B cut
of a B2C idea, the pick-and-shovel play beside the gold rush. This is **especially** the
move when the idea is a MISFIT (below): the literal framing may be wrong for this holder
while an adjacent framing they _can_ execute is hiding one step away, often inside the
opportunity signals the agents mined. Bold exploration lives in `## Viable variants` (label
each inference-only vs analyst-confirmed, with one concrete validation step); the primary
premise stays disciplined. Never manufacture a variant; if nothing adjacent is real, say so.

**Score strategic fit (conditional, cross-cutting, never a gate).** If step 1 captured
fit criteria (a target with a defined worth-it bar), score the surviving/reshaped idea
against them here: rate each criterion **FIT / STRETCH / MISFIT** with the specific idea
trait that meets or misses it, and land a one-line fit verdict. This is a **synthesis the
forge computes** — the fan-out agents stayed blind to the target so the world-viability
signal is uncontaminated; fit is a separate axis laid beside it. A world-VIABLE idea can
be a MISFIT, and a modest idea can be a strong FIT. Report both honestly and **never let
fit silently prune a branch or drop the idea**. The smith weighs the two axes. If no fit
criteria were captured, skip the score and carry fit as a caveat.

## Step 6. Smith checkpoint

Present, concisely: the evolved premise (and the grounded options from step 5), what
was pruned and why, emergent variants/wedges, the open questions, **the strategic-fit
verdict against the target** (if one was captured — stated as a distinct axis from
world-viability, so "viable but a MISFIT for you" reads clearly), **and a recommended
pipeline transition** (e.g. "promote raw → explored", "this reads like decided:kill").
Then the user decides:

- **Stop** — the idea is viable enough, or clearly dead.
- **Keep this direction** — forge another round on the evolved premise.
- **Redirect** — pursue one of the variants/options instead.
- **Fork** — the premise has drifted into a genuinely different idea (crossed
  target/customer/domain); spin it out as a new lineage-linked file (step 8) and leave the
  parent as-is.

Forge does not apply the transition or write a verdict itself — the user does. This
checkpoint is the cooperative core; the user's steer drives the next round.
