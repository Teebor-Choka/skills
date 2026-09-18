# Cross-agent fan-out — running the forge on Claude Code, Codex, or OpenCode

Forge's engine _is_ orchestration: it fans out independent stress-test agents, one per
branch, bounds how many run at once, then synthesizes and prunes their structured
verdicts. `SKILL.md` describes that as portable intent; this file binds the intent to
each agent's real mechanism. Read it before step 4 (spawning the squad).

For the general cross-agent theory — how subagents, parallel fan-out, deterministic
orchestration, and headless runs map across the three agents — see the **skill-creator**
skill (`references/workflows.md` and `references/triggering.md`). This file only covers
what is specific to forge's fan-out/prune/loop; it does not restate that groundwork.

## Contents

- The portable shape (the invariant every agent must honor)
- Claude Code — the Agent tool and the Workflow tool
- Codex — role-specialized subagents and `codex exec`
- OpenCode — the `task` tool and `opencode run`
- Bounding parallelism (cost guardrail)
- Synthesizing and pruning the results

## The portable shape (the invariant)

However you wire it, the fan-out must preserve four properties. They are what make the
result trustworthy — an implementation that drops one of them is not running the forge:

1. **One agent per branch.** Each agent attacks exactly one load-bearing claim (branch
   mode) or scores exactly one option (comparative mode).
2. **Concurrent and blind.** Agents run at the same time and never see each other's work.
   Independent convergence is the signal; sequential or shared-context runs contaminate it.
3. **Structured return.** Every agent returns the verdict schema
   (`forge-verdict.schema.json`) or, in comparative mode, the candidate schema
   (`forge-compare.schema.json`) — not free prose. Structured returns are what the
   synthesis step can dedupe, tally, and prune mechanically.
4. **Bounded width.** Never spawn more agents than the kernel has load-bearing claims
   (3–6 typical; 1 for a gut-check). Width is a cost lever, not a quality lever.

Bind these to whichever agent you are on below.

## Claude Code — the Agent tool and the Workflow tool

Two mechanisms, chosen by rigor.

- **Model-driven fan-out (default).** Issue several `general-purpose` (or a custom
  `forge-stress-tester`) subagent calls **in a single message** so they run concurrently.
  Give each the branch mandate verbatim from `forge-tactics.md`, the shared grounding, and
  the branch it owns; request the verdict schema as its structured output. The subagents
  can web-research and invoke the `deep-research` skill scoped to their branch.
- **Deterministic orchestration (thorough runs).** Use the **Workflow** tool for a real
  find → adapt → prune → re-test loop: `parallel()` to fan the branches out, the verdict
  schema as each agent's `StructuredOutput`, then a synthesis step that tallies verdicts,
  applies ADAPT/PRUNE, and (looping) re-tests only what changed. This skill authorizes the
  Workflow tool for that structured pass. A custom subagent definition lives in
  `.claude/agents/<name>.md`; the deep grounding pass is the `deep-research` skill.

Headless / CI: `claude -p "Use the forge-idea skill to stress-test: <kernel>"`.

## Codex — role-specialized subagents and `codex exec`

Codex has no workflow scripting engine, so the loop is driven from the shell.

- **Parallel fan-out.** Launch one `codex exec` process per branch (background them, then
  wait), each with the branch mandate and grounding, each asked to emit the verdict schema
  as JSON. Capture with `--json` / `-o out.txt` and pin a profile (`-p`) for determinism.
- **Role specialization.** Define subagents with distinct configs/tool access (e.g. a
  research role with MCP web access) so a stress-tester and a grounding pass are separate
  roles rather than one prompt.
- **Loop.** Parse each JSON verdict, run the synthesis/prune in the shell (or a small
  `scripts/` helper), and re-test changed branches with `codex exec resume` to carry
  round-to-round state.

## OpenCode — the `task` tool and `opencode run`

- **Parallel fan-out.** Either invoke the built-in `task` tool once per branch (a
  read/research subagent per branch), or launch multiple `opencode run` processes, one per
  branch, each returning the verdict schema as JSON (`-f json`). `subagent_depth` (default
  1. bounds nesting — keep the stress-testers at depth 1 so a branch agent does not itself
     fan out unboundedly.
- **Roles.** Define a stress-tester subagent in `.opencode/agents/<name>.md` with
  read/webfetch permission and `edit: deny` (it researches, it does not write files).
- **Loop.** Collect the JSON verdicts, synthesize/prune, and continue with
  `opencode run --continue` / `--session`, or keep a `serve --attach` server for state.

## Bounding parallelism (cost guardrail)

The expensive failure mode is the **double fan-out**: a grounding research pass, plus N
branch agents that each run their own research pass. Bound it:

- _Gut-check:_ 1 branch (the riskiest), 1 round, **no** nested research pass. Fail fast and
  cheap; only fan out the rest if the riskiest branch survives.
- _Thorough:_ 5–6 branches, orchestrated loop, nested research allowed.
- Never fan out wider than the kernel's load-bearing claims — width past that buys
  redundancy, not signal.
- Confirm the kernel before spending any fan-out (the confirm-the-kernel gate in step 1);
  a mis-aimed kernel wastes the whole squad.

## Synthesizing and pruning the results

Once the structured verdicts return (regardless of agent), the synthesis is identical — it
is the same step 5 in `SKILL.md`, driven by the schema fields:

- **Tally** verdicts (VIABLE / ADAPT / PRUNE) or scores (comparative mode).
- **Prune** every PRUNE branch into the `## Dead ends` ledger so it is not re-tested.
- **Apply** each ADAPT's `adaptation` and fold in the `opportunity_signals`.
- **Read convergence vs split.** Where independent agents agree, confidence is high; where
  they split, surface the split as a finding — do not average it.
- **Loop** by re-testing only materially-changed or new branches (step 8); carry
  VIABLE branches forward untouched.

Because the return is structured, this synthesis can be a script (`scripts/`) shared across
all three agents, with only the fan-out wiring differing per agent — the most portable and
testable form.
