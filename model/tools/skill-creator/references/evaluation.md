# Evaluating a skill

A skill is written once and run many times, so judge it on held-out prompts, not on the one
example you had in mind. Two things are worth measuring: does it **trigger** on the right
prompts (and stay quiet on near-misses), and does it **improve the outcome** versus no skill.

## A. Outcome evals (does the skill help?)

### 1. Test prompts

Write 2–3 realistic prompts a real user would actually type — concrete, with file names and
context, not "format this data". Save them to `evals/evals.json` (schema in
`assets/evals.example.json`): an array of `{id, prompt, expected_output, files, assertions}`.
Skip this for purely subjective skills (writing style, design) — judge those qualitatively.

### 2. Run with vs without the skill

For each prompt, run it twice on the target agent: once with the skill available, once without
(the baseline). Keep outputs side by side. If you have subagents, launch all runs in parallel;
otherwise run serially. Save outputs under a workspace, one dir per iteration and per eval:
`workspace/iteration-1/<eval-name>/{with_skill,without_skill}/`.

Run it on **each agent you target**, because triggering and tool availability differ:

```bash
# Claude Code
claude -p "<prompt>"                    # with skill installed vs a checkout without it

# Codex
codex exec -o out.txt "<prompt>"        # $skill for explicit; plain prompt for implicit

# OpenCode
opencode run -q -f json "<prompt>"
```

### 3. Assertions (objective checks)

For anything verifiable, write named assertions and check them with a script, not by eye —
scripts are repeatable across iterations. Good assertions read clearly ("output CSV has a
`margin_pct` column", "no file outside `src/` was modified"). Don't force assertions onto
subjective quality; review those by hand.

### 4. Grade, compare, iterate

Grade each run against its assertions; compare with-skill vs baseline on pass rate (and, if you
care, time and tokens). Read the _transcripts_, not just final outputs — if the skill made the
agent do wasteful work, cut the part that caused it. Then improve and re-run into
`iteration-2/`. Generalize from failures (reframe, explain the why) rather than overfitting a
rule to one prompt. Stop when the user is satisfied, the deltas flatten, or assertions all pass.

## B. Trigger evals (does it fire at the right time?)

The `description` decides invocation, so test it directly. Write ~20 realistic queries split
between **should-trigger** (8–10; varied phrasings, casual and formal, some not naming the
skill) and **should-not-trigger** (8–10 near-misses — queries that share keywords but need a
different tool). Avoid obvious negatives; the near-misses are what tune the description.

Run each query against the agent with the skill installed and record whether it loaded the
skill. Run each a few times (triggering is probabilistic) and take the rate. Then adjust the
`description`: add missing trigger phrasings for false negatives, add scope/"do not use for…"
language for false positives. Re-run. Note that trivial one-step queries may not trigger any
skill on any agent (the model just does them), so keep queries substantive.

## C. Fast static checks (every iteration)

Run `scripts/validate_skill.py <skill-dir>` before each eval round. It checks the portable
contract cheaply: `name` regex and dir match, `description` present / under 1024 / no angle
brackets, only portable frontmatter keys in the core, and a lint for agent-specific tool calls
(`Task(`, `@"… (agent)"`, `skill({`) leaking into the portable body. Fix these before spending
an eval run on them.

## Cross-agent parity

When a skill targets more than one agent, run the outcome and trigger evals on each. Common
divergences to watch: a skill that triggers on Claude Code under-triggers on Codex/OpenCode
because the description leaned on Claude phrasing; a body that assumed a Claude tool call
silently no-ops elsewhere; hooks/commands that exist on one agent and not another. Keep the
portable core identical across agents and let only the adapters differ.
