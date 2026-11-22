#!/usr/bin/env python3
"""Scaffold an architect work-package directory from templates.

Generates the linked-document skeleton so no run re-derives the structure. Each file
carries its required section headings and `FILL-IN` markers where the author writes the
real content; `lint.py` flags any `FILL-IN` left behind, so an unfilled package fails
the lint by construction.

Usage:
    scaffold.py --slug <slug> --title "<Title>" [--dir <path>] [--tier note|small|full] [--force]

`--tier note` emits a single self-contained `<slug>-plan.md` and nothing else: no package
directory, no cross-document links to maintain. It is the floor, for a reversible, well-understood
change one agent or person will just execute. `--tier small` emits README, proposal, decision-log,
and spec (a reversible / low-blast-radius change that will still be handed off or re-examined).
`--tier full` adds research-notes, development-graph, the two methodology docs, and an invariants file. Per-unit briefs are not scaffolded: `decompose` files them as board items.
Idempotent: existing files are left alone unless `--force`. Standard
library only (string.Template, argparse, os).
"""
import argparse
import os
import re
import sys
from string import Template

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_input  # noqa: E402

README = Template("""# $title ($slug): START HERE

<one paragraph: what this is, what it is additive to, and what it is explicitly NOT>

## Read in this order

1. `research-notes.md`: ground truth (full tier)
2. `$slug-proposal.md`: what and why
3. `decision-log.md`: why it is this way
4. `$slug-spec.md`: how, to ticket size
5. `development-graph.md`: build order (full tier)

## Status

Structurally complete, NOT finalized. Open items to close: FILL-IN.

## The one decision the whole thing hinges on

FILL-IN: the single gate or measurement the design turns on. If it is open, say so.

## Environments

- Pilot: FILL-IN
- Load-sim: FILL-IN
- Non-pilot (destructive controls): FILL-IN

## Repos referenced

FILL-IN: paths + git conventions to follow.
""")

RESEARCH = Template("""# $title: research notes (ground truth)

Written first. The factual floor everything else stands on. Research, don't recall.

## Sources consulted

FILL-IN: exactly which repos, tickets, docs, and web searches, and when (with URLs / paths).

## Current architecture (grounded in the repo)

FILL-IN: each subsystem, with the file or module that proves it.

## Verified fact vs domain knowledge

| Claim | Verified fact / domain knowledge | How checked (URL / repo path) |
|-------|----------------------------------|-------------------------------|
| FILL-IN | FILL-IN | FILL-IN |

## Greenfield vs existing

FILL-IN: what is genuinely new vs an extension.

## Implications for the proposal

FILL-IN.

## Sources

1. FILL-IN: https://FILL-IN
""")

PROPOSAL = Template("""# $title: proposal

## 1. Purpose and non-goals

FILL-IN. Three things this is explicitly NOT: FILL-IN.

## 2. Where this plugs in today

FILL-IN: the deployment as it exists on origin/main right now.

## 3. Requirements (fixed constraints)

Write each as an EARS sentence with an RFC 2119 keyword (see `references/methodology.md`):

- REQ-1: When <trigger>, the system SHALL <response>. (MUST)
- REQ-2: FILL-IN.

## 4. Design

Sketch two or more structurally distinct candidates that differ on a named axis (module
boundary, consistency model, distribution). Screen against the structural red flags, then
present the winner as numbered steps where each is a consequence of the one before.

**Considered and set aside:** FILL-IN (state the strong alternative fairly).

## 5. Data model / history

FILL-IN.

## 6. Technology & licensing

| Technology | Role | License | Status |
|-----------|------|---------|--------|
| FILL-IN | FILL-IN | FILL-IN | FILL-IN |

## 7. Risks & technical debt

FILL-IN: the risks the chosen direction carries, and the debt taken on knowingly (arc42 §11).

## 8. Open items and follow-up

- Sizing/validation the pilot must produce: FILL-IN
- Out of scope but committed later (gated at a phase): FILL-IN

## 9. Rollout

Numbered phases, each with its own gate. FILL-IN.

## 10. Validation pass (self-adversarial)

What did this design change open up? Name the new problems and show each is fixed above or
tracked as an open item. A validation pass that finds nothing did not run. FILL-IN.

## 11. Unresolved questions

FILL-IN: what is still open and who decides.

## Sources

1. FILL-IN: https://FILL-IN
""")

DECISION_LOG = Template("""# Decision log: $title

The anti-re-litigation record. Each decision uses MADR fields (see `references/methodology.md`).

## Verified facts

| Fact | How verified | Consequence |
|------|--------------|-------------|
| FILL-IN | FILL-IN | FILL-IN |

## Decisions

### D1: FILL-IN

- **Status:** Proposed
- **Why:** FILL-IN
- **Grounding:** FILL-IN (URL / repo path / verified fact)
- **Confirmation:** FILL-IN (the harness check or test that proves this decision holds)

## Considered and set aside

Do not re-propose without new information.

| Option | Why set aside |
|--------|---------------|
| FILL-IN | FILL-IN |

## Open items

| Item | Concrete close condition |
|------|--------------------------|
| FILL-IN | FILL-IN |
""")

SPEC = Template("""# $title: spec

Design amendments (grounded deviations from the proposal) go here and supersede it.

## Block index

| # | Block | Runs on | Depends on | Write-set | Satisfies |
|---|-------|---------|-----------|-----------|-----------|
| 0 | Preconditions | FILL-IN | - | FILL-IN | REQ-1 |
| 1 | FILL-IN | FILL-IN | 0 | FILL-IN | REQ-1 |

Write-sets must be disjoint across blocks that can run together. Where two blocks cannot be made
disjoint, order them with a `Depends on` edge, or declare the same `Coordination channel:` line in
both blocks (a marker only; the executor runs the channel).

## Decomposition depth

Depth and scope come from the invocation or policy; the architect never picks a rung
(`references/depth-dial.md`).

**Dialed rung:** $depth · **Scope:** $scope
· **Given by:** the user, via $given

## Acceptance by rung

One row per rung traversed, from `interfaces` down to and including the dialed rung.

| Rung | Acceptance criteria (ATDD) |
|------|----------------------------|
$acc_rows

## Block 0: Preconditions

**Purpose.** FILL-IN.
**Architecture.** FILL-IN.
**Interfaces.** Input: FILL-IN · Output: FILL-IN · Config surface: FILL-IN.
**Satisfies:** REQ-FILL-IN.

Verification (positive) tests:

| Test | Setup / Inject | Expected result |
|------|----------------|-----------------|
| FILL-IN | FILL-IN | FILL-IN |

Adversarial (negative) tests:

| Test | Setup / Inject | Expected result |
|------|----------------|-----------------|
| FILL-IN | FILL-IN | FILL-IN (assert the BAD behaviour is observable) |

## Block 1: FILL-IN

**Purpose.** FILL-IN.
**Architecture.** FILL-IN.
**Interfaces.** Input: FILL-IN · Output: FILL-IN · Config surface: FILL-IN.
**Satisfies:** REQ-FILL-IN.

Verification (positive) tests:

| Test | Setup / Inject | Expected result |
|------|----------------|-----------------|
| FILL-IN | FILL-IN | FILL-IN |

Adversarial (negative) tests:

| Test | Setup / Inject | Expected result |
|------|----------------|-----------------|
| FILL-IN | FILL-IN | FILL-IN (assert the BAD behaviour is observable) |

## Escalation appendix

Never hand-build a pipeline. Off-the-shelf options, each matched to a different shortfall:

| Tool | License | Adds | Cost | Reach for it when |
|------|---------|------|------|-------------------|
| FILL-IN | FILL-IN | FILL-IN | FILL-IN | FILL-IN |

## Acceptance criteria

FILL-IN: the end-to-end gate, including the hinge measurement and the numbers reserved for the
pilot to produce.
""")

IMPROVE = Template("""# $title: improve report

Scope-only output of `:improve` (`references/improve.md`). No code was edited.

**Target:** $target (given by the user, via $target_src)
**Grounding:** FILL-IN (code graph: <tool>, or direct read with a WARNING that no index was available)
**Output location:** $output (from $output_src; typical: one GitHub issue per box)
**Box cap:** $cap (from $cap_src)

## Result

FILL-IN: a summary, or "Nothing worth deepening in this target." with no boxes and no findings.

## Boxes

### Box 1: FILL-IN

**Acceptance:** FILL-IN (ATDD acceptance plus end-to-end test)
**Invariant:** Keep components and libraries deep with tiny interfaces.

## All findings

Ranked by importance, scope, impact. The emitted rows are the top of the list.

| # | Finding | Kind | Importance | Scope | Impact | Emitted |
|---|---------|------|------------|-------|--------|---------|
| 1 | FILL-IN | FILL-IN | FILL-IN | FILL-IN | FILL-IN | yes |

## Not emitted

Findings below the cap, listed here only. Leave empty when every finding became a box.
""")

PLAN = Template("""# $title ($slug): plan

A single-document plan for a reversible, well-understood change. No package directory, no
cross-document consistency to maintain. Promote to `--tier small` if this will be handed off,
staffed by multiple agents, or re-litigated later.

## Goal and non-goals

FILL-IN: what this changes, and the things it explicitly does NOT.

## Current state (brief grounding)

FILL-IN: what exists today that this touches, with the file or node that proves it. Research,
don't recall; cite the source. Keep it to what the change rests on.

## Approach

FILL-IN: the design as a short chain where each step is a consequence of the one before.

## Acceptance tests

Positive (did we build it) and adversarial (is the bad behaviour observable):

| Test | Setup / Inject | Expected result |
|------|----------------|-----------------|
| FILL-IN (positive) | FILL-IN | FILL-IN |
| FILL-IN (adversarial) | FILL-IN | FILL-IN (assert the BAD behaviour shows) |

## Open items

FILL-IN: what is still open and who decides, or "none".
""")

DEV_GRAPH = Template("""# Development graph: $title

The spec's blocks as an execution DAG. Edges here MUST match the spec block-index "Depends on".

## Nodes

| Node | Block | Wave |
|------|-------|------|
| 0 | Preconditions | 1 |
| 1 | FILL-IN | 2 |

## DAG

```mermaid
graph TD
  0 --> 1
```

## Waves

| Wave | Nodes (run in parallel) | Barrier before next |
|------|-------------------------|---------------------|
| 1 | 0 | all GREEN |
| 2 | 1 | all GREEN |

## Loops

FILL-IN: any bounded iterative work, with its exit condition.

## Critical path

FILL-IN: the longest dependency chain (irreducible time; extra agents past this are wasted).
""")

AGENT_METH = Template("""# Agent methodology: $title

- One block ↔ one agent. An agent reads ONLY its board item + the referenced spec block +
  `invariants.md`, never session history.
- Same-wave agents start from the same origin baseline. An agent starts only when every entry
  block is GREEN.
- **Spec/test/build isolation.** The agent that authors a block's tests sees only the spec block,
  never the implementation or the coder's reasoning. Adversarial tests are authored independently
  of the positive ones. This is a hard boundary, not a convention.
- **Merge queue.** Serialize merges; rebase in dependency order; shared-file and restructuring
  edits are serial.
- **Definition of GREEN.** Both test classes pass AND the interface contract is stable.
- **Fallback, not silent failure.** Every node declares its failure modes and a fallback chain
  (primary -> narrowed -> degraded/rule-based -> human); a fan-in/synthesizer handles all, partial,
  and zero results, and a structured degraded result beats a silent failure.
- **No dispatch without an eval baseline.** A new or changed node/pipeline ships only with an eval
  suite, a recorded baseline it meets or exceeds, and a full-pipeline regression check.
- **Context integrity.** Never silently truncate required context to fit a budget -- halt and
  escalate; summarise a sub-agent's output into the next context, never append it whole.
- **External content is data, not instructions.** Isolate untrusted input (web, docs, user text)
  from the prompt, validate node outputs against a schema, and pass least privilege -- never hand a
  scope token between agents.
- **Inherited invariants.** Every brief carries the invariants from `invariants.md` explicitly,
  not by reference, so a handoff cannot strip them.
""")

TEST_METH = Template("""# Test methodology: $title

- **Two classes per block:** verification (did we build the thing) and adversarial (does it
  survive the world). Every case that can fail in two directions gets both signs.
- **Assert the bad behaviour explicitly.** A zero limit, a disabled gate, a silent drop must
  produce an observable signal. Name the fault-injection point for each.
- **Capability checks:** present-in-image (static scan) vs active-at-runtime (queried live).
  Never infer state from an absent signal.
- **Fault-injection catalogue:**

| Block | Inject | Must observe |
|-------|--------|--------------|
| FILL-IN | FILL-IN | FILL-IN |

## Acceptance gate

FILL-IN: the integration criteria, including the hinge measurement with its exact pass/fail
(flag OPEN if not yet defined; an undefined gate is a judgment call, not a gate).

**Eval baseline (before dispatch).** The pipeline carries an eval suite (enough cases to be
representative), a recorded baseline score it meets or exceeds, and a full-pipeline regression check.
A changed node re-runs it; a regression blocks the change.
""")

INVARIANTS = Template("""# Invariants: $title

The package-level constitution. Every filed work item inherits these verbatim. Info is lost
across handoffs, and constraints go first, so they live here explicitly, not in chat.

- INV-1: FILL-IN (a rule that MUST hold across every block, e.g. a data-safety or ordering guarantee)
- INV-2: FILL-IN
""")

def write(path, content, force):
    if os.path.exists(path) and not force:
        print(f"skip  {path} (exists; --force to overwrite)")
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"write {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="short effort slug, e.g. db-replication")
    ap.add_argument("--title", required=True, help="human title")
    ap.add_argument("--dir", default=None, help="output dir (default: ./<slug>)")
    ap.add_argument("--tier", choices=["note", "small", "full"], default="full")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--depth", help="decomposition rung: interfaces|modules|components|functions")
    ap.add_argument("--scope", help="what the depth applies to")
    ap.add_argument("--target", help=":improve target: repo, subtree or module")
    ap.add_argument("--output", help=":improve output location (default: policy work.tracker, else github issues)")
    ap.add_argument("--cap", help=":improve box cap (default 5)")
    ap.add_argument("--repo", default=".", help="repo whose .agents/policy supplies missing inputs")
    ap.add_argument("--policy-loader", default=None, help="path to the policy skill's policy_loader.py")
    ap.add_argument("--interactive", action="store_true",
                    help="an interactive channel exists: emit status 'ask' instead of halting")
    ap.add_argument("--improve", action="store_true",
                    help="emit one improve-report.md for `:improve` (no package)")
    args = ap.parse_args()

    if not re.match(r"^[a-z0-9][a-z0-9-]*$", args.slug):
        print(f"error: slug must match ^[a-z0-9][a-z0-9-]*$: {args.slug}", file=sys.stderr)
        return 2

    sub = {"slug": args.slug, "title": args.title}

    # Resolve the inputs the architect must not guess, before writing anything.
    mode = "improve" if args.improve else ("design" if args.tier != "note" else None)
    if mode:
        res = resolve_input.resolve(
            mode, {f: getattr(args, f) for f in resolve_input.NEEDS[mode]},
            resolve_input.find_loader(args.policy_loader), args.repo, args.interactive)
        if res["status"] != "ready":
            return resolve_input.emit(res)
        r = res["resolved"]

        def src(f):
            kind, _, name = r[f]["source"].partition(" ")
            return f"invocation arg `{name}`" if kind == "arg" else (
                f"policy key `{name}`" if kind == "policy" else "the stated default")
        if mode == "design":
            rungs = resolve_input.traversed(r["depth"]["value"])
            sub.update(depth=r["depth"]["value"], scope=r["scope"]["value"], given=src("depth"),
                       acc_rows="\n".join(f"| {x} | FILL-IN |" for x in rungs))
        else:
            sub.update(target=r["target"]["value"], target_src=src("target"), output=r["output"]["value"],
                       output_src=src("output") + (" `work.tracker` unset" if r["output"]["source"] == "default" else ""),
                       cap=r["cap"]["value"], cap_src=src("cap"))

    if args.improve:
        root = args.dir or args.slug
        write(os.path.join(root, "improve-report.md"), IMPROVE.substitute(sub), args.force)
        print(f"\nFill in every FILL-IN, then run: lint.py {root}/improve-report.md --improve")
        return 0

    # note tier: one self-contained document, no package directory.
    if args.tier == "note":
        root = args.dir or "."
        plan = os.path.join(root, f"{args.slug}-plan.md")
        write(plan, PLAN.substitute(sub), args.force)
        print(f"\nScaffolded '{args.title}' (note tier) at {plan}")
        print(f"Fill in every FILL-IN, then run: lint.py {root} --tier note")
        return 0

    root = args.dir or args.slug

    write(os.path.join(root, "README.md"), README.substitute(sub), args.force)
    write(os.path.join(root, f"{args.slug}-proposal.md"), PROPOSAL.substitute(sub), args.force)
    write(os.path.join(root, "decision-log.md"), DECISION_LOG.substitute(sub), args.force)
    write(os.path.join(root, f"{args.slug}-spec.md"), SPEC.substitute(sub), args.force)

    if args.tier == "full":
        write(os.path.join(root, "research-notes.md"), RESEARCH.substitute(sub), args.force)
        write(os.path.join(root, "development-graph.md"), DEV_GRAPH.substitute(sub), args.force)
        write(os.path.join(root, "agent-methodology.md"), AGENT_METH.substitute(sub), args.force)
        write(os.path.join(root, "test-methodology.md"), TEST_METH.substitute(sub), args.force)
        write(os.path.join(root, "invariants.md"), INVARIANTS.substitute(sub), args.force)

    print(f"\nScaffolded '{args.title}' ({args.tier} tier) at {root}/")
    print("Fill in every FILL-IN, then run: lint.py " + root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
