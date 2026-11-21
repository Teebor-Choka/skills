---
name: implement
description: >
  Implement a feature or fix a bug or issue (an issue URL, "implement #N", "add X") with TDD,
  adversarial review and merge gate. Load before the first code edit. Not for typos,
  docs-only edits or questions.
metadata:
  version: "0.2.0"
  group: swe-workflows
  siblings: [triage, find-bug]
---

# implement — the per-task SWE loop

Carry **one work item** to an integrated change. The steps are fixed; the _specifics_
(which test discipline, how strict the gate, solo vs fleet) come from the repo's
**policy**, and each gate **enforces** that policy rather than trusting the implementer.

Two things make this real rather than ceremony:

- **Policy-driven, not hardcoded.** Read `practices` / `gate` / `mode` from `.agents/policy`
  (via the loader of the `policy` skill, from the `harness` plugin: `harness:policy`). The discipline lives in data, so it is per-repo and
  per-file, not baked into this skill. Default `practices: {scope: ATDD, task: TDD}`.
  **A repo with no `.agents/policy` runs the loop on these defaults.** A missing policy removes
  the repo's gates, not the steps: spec check, test-first, quality pass, isolated review and the
  review loop all still apply. Never skip the skill because the policy file is absent.
- **Enforcement is external to you.** A gate you grade yourself is theater. Every gate below
  resolves its policy key through `scripts/policy-gate.sh` and is backed by something that
  cannot be talked into a shortcut: CI, the quality tool's own numbers, an **isolated**
  reviewer, the external review bot, and git's own history (the failing-test commit).

Read `references/disciplines.md` for the TDD/ATDD/spec/review craft, `references/bindings.md`
for the forge mapping, `references/enforcement.md` for how each gate blocks, and the `policy`
skill (`harness:policy`, `ai/harness` in this repo) for the loader contract.

## The loop

```
take work item
  → spec check            holes → request detail on the item OR escalate to triage
  → implement             ATDD → TDD; functional red before green; gotcha → new work item OR escalate
  → quality check         project's own method, else the skill policy key `quality` names
  → update project documentation   improve the docs this change invalidates; run the docs validator if the project has one
  → adversarial review    a separate, isolated reviewer — never self-grade
  → open change request → ready        ← handover point
  → review loop           defend when right; defer out-of-scope as new work items
  → all green → integrate CI + automated review clean
  → retrospective         findings become work items; durable lessons → skill / AGENTS.md / memory
```

Resolve policy once at the start: `scripts/policy-gate.sh <repo> show` prints the resolved
`practices`, `gate`, `mode`. Pass the touched file as `--target` so per-file rules apply.

### 1. Take a work item

Pull one item from the tracker (binding: GitHub issue, beads, …). One item → one branch →
one change request. If `mode: team`, claim it first per the orchestration process (ownership
is durable in the tracker, never only in a session).

### 2. Spec check

Before any code, confirm the item carries acceptance criteria (valid inputs, the exact
"done", failure behaviour). A blank category becomes a default no one approved. If it is
under-specified: **request detail on the item**, or **escalate to the `triage` dispatcher**
(design resolver/stakeholder) to resolve or escalate further. Never code against an unspecified
item — unspecified resolves to the most literal plausible reading, which is rarely what was
meant. If the request has no done-when, run `triage`'s spec questions inline (at most 3), then
continue. Before you ask the user, write 3-5 sentences in chat naming the artifact, the fork and the
cost of each branch, then ask with plain-language options. Before you leave plan mode, print
`Assumed scope:` repos, hosts, secrets path, out of scope.

### 3. Implement (ATDD → TDD)

Drive from `practices`. With `scope: ATDD`, start from the agreed acceptance tests at the
unit's public contract; with `task: TDD`, fill them in red → green → refactor at the unit
boundary. Build **from the acceptance tests down to unit tests**.

- The red must be a **functional failure, not a compile error.** A test that does not compile
  is not a red; it must run and fail because the behaviour is absent or wrong. Commit the
  failing test before the implementation — that commit is the artifact the review gate checks.
- **Surgical diff.** Every changed line traces to the item. Remove only the orphans your own
  change created.
- **Gotcha** (an out-of-scope bug, a missing dependency, a design ambiguity): **file a new
  work item** (linked) or **escalate to the orchestrating LLM**. Never silently widen scope
  or guess a destructive/ambiguous call.

Keep the context small while you work:

- In an indexed repo, load the code-graph tools first (in Claude Code: `ToolSearch` with
  `select:mcp__codebase-memory-mcp__search_graph,mcp__codebase-memory-mcp__get_code_snippet`), before
  the first whole-file read.
- For a file over about 20 KB, use a ranged read around the symbol the graph found, or the graph's
  `get_code_snippet`, not a whole read. Filter `gh pr view` output with `--json` and `--jq`.
- After the 2nd compaction, and at turn end with work pending, write `.agents/handoff.md` (done,
  next, blocked, how to verify). Then start a fresh session from it.
- Wrap a long build or test command so only failures print (for example, send the output to a
  log file and print its failing lines). Never print a passing run in full.

### 4. Quality check and update project documentation

Run the project's **own** quality method if it has one (its gate, its thresholds); otherwise
invoke the skill policy key `quality` names on the change. Verify each flagged finding — a threshold
crossing is a candidate, not a verdict. This gate resolves `gate`; `gate: tests` means the
project's tests/metrics must pass before proceeding.

**Update project documentation.** Update and improve the project documentation for every change.
A change that alters documented behaviour, structure, or a recorded decision leaves the docs wrong
until they catch up. If the project documents itself (an overview, a spec, a decision log), update
the parts this change invalidates: the architecture or overview when structure moves, the spec and
the decision record when an invariant or decision changes, any acceptance or KPI matrix when
behaviour changes. Run the project's docs validator if it has one (for example a `validate_docs.py`
wired into CI and pre-commit). A project that does not document itself makes this a no-op: do not
impose docs it never had. The validator machine-checks structure; that the content actually
reflects the change is confirmed by the adversarial reviewer (step 5), the same way the functional
red is.

Two cases that the paragraph above does not leave to judgment:

- **A change adds a subsystem** (a new module, service, pipeline or stage, not a change inside an
  existing one) in a project with no `docs/`: invoke `project-docs` to write the overview, and the
  decision record for the choice the change embodies. Do not backfill unrelated parts.
- **A change touches a process document**: `.agents/policy.md` or `.agents/charter.md`. The same
  change adds an iteration record, `.agents/iterations/NNNN-<slug>.md`, with its reason, the metrics
  it should move, their direction, the window, and the documents it touches. A change to the process
  is a change request like any other, and the owner's merge is the approval.

### 5. Adversarial review (local, isolated)

Hand the diff to a **separate, isolated reviewer** — a different context that cannot inherit
your rationalizations (delegate it to an isolated subagent or a fresh worktree review; the
adapter wires the mechanism). It reads **boundaries and error paths first**, verifies each
finding, confirms the step-3 red was a real functional failure, and checks that the docs updated
in step 4 actually reflect the change. The author never grades their own work. Address confirmed
findings before marking ready.

### 6. Open the change request → mark ready

One change request, conventional title, linking/closing the work item (one `Closes #N` per
line). It is a **handover
point**: another session may run the review loop, so the description must stand alone (what,
why, how verified). Draft until the local gate is green and steps 4–5 are addressed; then start
the binding's **watch change request** watcher, which marks it ready and drives step 7. Don't start
the watcher earlier: starting it is the ready decision. Ready means the implementation is complete
and feedback is requested. It does not predict CI or review results; those arrive afterwards as
watcher events, and the change request stays ready while you address them.

### 7. Review loop

Address the external review bot and any remaining adversarial findings. Loop until clean and
checks green. Drive the loop from the binding's **watch change request** watcher, which prints
only new feedback, settled checks and base drift, and keep it running until the change request
is integrated or closed; never poll the forge by hand. On GitHub the watcher is one Monitor on
`git:workflow`'s `scripts/babysit`, one per change request, on the haiku tier. Load Monitor first
(`ToolSearch select:Monitor`), re-arm it on exit 144 (host expiry), and read
`.git/babysit/<branch>.json` before re-arming after a crash. Never use `ScheduleWakeup` or a
`gh pr view` loop; `scripts/pr-state` gives a single look. A check that fails on two unrelated
change requests gets one owner and a repro, not `gh run rerun`. Two rules:

- **Defend when right.** A review comment that is wrong gets a reasoned reply on the thread,
  not a reflexive change.
- **Defer out of scope.** In-scope fixes land now; larger or out-of-scope findings become
  **new work items**, linked — the change request does not balloon.

### 8. All green → integrate

"Green" is CI **and** the automated review/feedback clean — not CI alone. Then integrate per
the merge policy (`mode: team` → the orchestration dial; `mode: single` → integrate on green).
Integrating closes the work item and prunes the branch/worktree.

### 9. Retrospective

Capture what the item taught. **Findings become work items** in the tracker. Route durable
lessons by the standing order: the relevant **skill** first, then the nearest **AGENTS.md**,
then **memory** (behaviour preferences only). For each plan or review rejection, name the file
where the missing fact belongs and write the line; the rejection text is the draft. The loop edits the world outside this session
so the next one starts better.

## Enforcement (summary)

Each gate calls `scripts/policy-gate.sh <repo> <gate> [--target FILE]`, which resolves the
policy key and exits non-zero when the policy is unmet. The hook (`hooks/gate.sh`) wires this at
**commit / ready / integrate** so it holds even when a session skips this skill: it asks the
forge binding (`scripts/forge-state.sh`) for the boundary's real state (at integrate: CI green +
review clean; ready is never gated on the forge), then **hard-blocks a genuinely unmet boundary in `mode: team`** and **warns in
`mode: single`**. Full mapping of key → gate → what blocks is in `references/enforcement.md`.

## Portability

The body names no agent's tools. "Delegate the adversarial review to an isolated reviewer" is
intent; each agent's adapter wires it (a subagent, a worktree, a fork). `scripts/` is POSIX +
Python 3 stdlib. The forge is named only in `references/bindings.md`.

## Group

`triage` (the spec-hole dispatcher to design resolver/stakeholder) and `find-bug` (the reproduction
loop, a reported defect to a committed functional red) are siblings in the swe-workflows group.
They feed this skill's existing gates rather than adding their own: `triage` produces a work
item that passes the spec gate; `find-bug` produces the functional red the commit gate and the
adversarial reviewer check for. For a bug fix, load `swe-workflows:find-bug` first.
