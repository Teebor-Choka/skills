---
name: reflect
description: Retrospective over agent sessions. Finds what to improve in friction, cost, skill dispatch, hooks, the user's own prompts, orchestration and metrics. Proposes fixes to the setup, never the work. Use for a retrospective or /reflect.
---

The user asked for a **retrospective**. Find nearly everything that can be better about the session or sessions in scope, not only where the agent struggled, and propose changes to the **setup**: the environment, instructions, skills, hooks, workflow, and the way the user prompts. You do not change the work itself. Take the mistake that shipped, the fact that took twenty tool calls to find, the prompt that left a gap, and ask what let it happen. You propose. Nothing changes until the user picks a candidate.

A **run** is one session plus every subagent it started, scored as a whole. Scripts count and anchor; you read only the flagged moments; every candidate traces to a logged line or is dropped. Script output is JSON on stdout, read-only on transcripts, secrets scrubbed. Run them with `python3 -I`. Transcript layout is an input adapter: [`references/adapter-claude-code.md`](references/adapter-claude-code.md). Another harness needs its own adapter; the lenses and rules below do not change.

## Steps

1. **Scope.** A single session (default) or a cross-session scope the user names. With no window for a cross-session scope, ask for one. A continued session is one run: pass all its transcripts with `--run`. An orchestrator's shared log goes in with `--coordination`. Add transcripts of other sessions to judge them too.
2. **Check what exists first.** Before proposing any control, read the current config, hook, skill or instruction file it would touch. An existing control that is unwired or too broad is the finding, not a new control. For a finding that names a file, run `fixed.py` (git log on the file): a finding last seen before the fix commit is FIXED. Do this before routing any model-tier, hook or skill fix.
3. **Measure, by lens.** Run the scripts named in the lenses below. Window by event time, never file mtime, and report each session's in-window share. State the basis of every share (per session or per turn). Re-check any dollar figure quoted from an earlier round.
4. **Read flagged moments only.** Read every human `steer` and `correction` in the main transcript. For a multi-agent run or many sessions, give each group (by agent type, plus the main transcript, plus run-level moments) to one cheap subagent that returns findings in the schema from [`references/friction-signals.md`](references/friction-signals.md). Quote only text a script wrote to a file, and check each quote against its source by exact match or sha256. If a compression proxy sits between you and the tools, turn it off for the run or say in the report that it was on. Ask for numbers as compact JSON, not prose tables.
5. **Synthesize.** Run `synthesize.py` over the findings from all readers and rounds: it groups by mechanism and flags opposite verdicts. A root-cause or REFUTED claim needs a full count, not a top-N sample, before it enters the ranking.
6. **Classify and route** each finding (below). A **mechanical** violation gets a check that can fail; prose is for judgement calls.
7. **Order by severity and present.** Recurrence is severity. Show positive outcomes and the good-versus-bad comparison beside the friction. Propose only.

## Lenses: a run covers each one

| Lens                           | What to look for                                                                                                                                                                               | Numbers from                                                               |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| User prompts and inputs        | Vague or late specs, corrections that restate the task, short "continue" loops (human as the loop), queued messages. Judge only `human` turns, never skill bodies, summaries or notifications. | `scan-sessions.py` (steers, corrections, `outcome.human_loop`), `drill.py` |
| Always-on instructions         | Size, dead lines, rules that load every session but fire rarely.                                                                                                                               | `context-audit.py --always-on`                                             |
| Skill dispatch                 | Offered versus used, per-skill rate, listing size and per-source share. Exclude hook-forced loads before blaming wording.                                                                      | `context-audit.py` (`skill_rates`, listing by source)                      |
| Hook outcomes                  | Deny versus non-blocking error versus context injection. A hook said to block that never denies.                                                                                               | `scan-sessions.py --summary --blocking-claims`                             |
| Tool misuse                    | Repeated reads and commands, errors, tools offered but never called (only if offered), a tool whose cost exceeds its return.                                                                   | `scan-sessions.py` (`tools`, errors), `context-audit.py`                   |
| Orchestration and coordination | Rework, failed or unfinished agents, outlier agent cost, peer messages, coordination events. Check the lead's sizing and briefs.                                                               | `scan-sessions.py` (members, `--coordination`), `drill.py --agent`         |
| Cost and context               | Dollars two ways (cost state, per-message usage), per model, compaction, context pressure.                                                                                                     | `cost.py`                                                                  |
| Session operations and metrics | Window share, turns, long-session share on both bases, weekly trend, first and last seen.                                                                                                      | `scan-sessions.py --summary`, per-run `weekly`                             |
| Positive outcomes              | What worked, so a fix does not break it: artifact produced, ended with evidence, abandoned. Compare friction of good and bad runs before routing.                                              | `scan-sessions.py --summary` (`outcomes`)                                  |

## Routing: where each fix lands

- **Long hunt for a file or fact:** a navigation pointer from a file already loaded.
- **A mistake a check could catch:** a deterministic check (linter, test, schema, hook, CI). Read the project's own check command first.
- **A judgement-call rule a review missed:** the relevant skill, then the nearest `AGENTS.md`, then a review step's standards. Never a bare line in always-loaded steering.
- **A skill or workflow step that misled:** fix the step, or the process (order, missing gate, sequential work that should fan out).
- **Steering bloat or no-ops:** move it into a skill or a check; delete lines that change nothing.
- **Expensive tool call for its return:** streamline or replace the tool.
- **Coordination failure, or agents costing more than they return:** the orchestrating skill's step, sizing or brief; a check there beats a sentence.
- **Information the agent could not reach:** widen access (tee a log, read-only access).
- **A weak or ambiguous user prompt:** a prompt template, an intake question in the skill that starts the work, or a one-line pointer for the user. Not a rule for the agent.

A new rule goes where it is read when needed, not into always-loaded steering.

## Guardrails

- **Anchor or drop.** Every candidate names a session and a transcript line. One you cannot trace is generic advice; discard it.
- **The check beats the sentence.**
- **Homes are:** a skill or workflow step, an `AGENTS.md` pointer, a deterministic check, a tool or MCP change, a widening of access. Memory only if the user asks.
- **Propose only.** No edits, hooks, commits.
- **Know who spoke.** In a subagent transcript the "user" is the agent that started it: its follow-ups are `rework`. Messages from other sessions are `peer`. Attribute a finding to the user only from a human `steer` or `correction` in a main transcript. Queued messages and waits on a human are not human friction until `classify_user_turn` says `human`.
- **Fix scope before strictness.** If a hook fires on too much, narrow its matcher first; only then make it block (exit 2). An exit 1 does not block.
- **A refuted claim stays out of the ranking.** Never quote a spend figure without its source (cost state or usage) and window.
- **Never print a secret.** Scripts scrub excerpts; scrub anything you copy by hand.
- **Say what you did not measure.** List the lenses with no data, and why.

## Roles

The scripts rank and anchor. A cheap subagent per group extracts findings from flagged moments; each false positive or miss it surfaces is a cue to sharpen a script. Synthesis, routing and severity are yours.
