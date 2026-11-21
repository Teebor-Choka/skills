# Metrics

The single definition of every number `metrics.py` and `report.py` print. Targets and alert
thresholds are in [`metrics.toml`](metrics.toml). Every metric is computed per window over the
session records, by each session's last event. Field names in the transcript are in the
adapter reference.

Baselines quoted from the originating analysis (one user, one month) are examples of the order
of magnitude, not targets for your setup. Re-derive them from your first report.

## Session record

`metrics.py record <transcript>` prints exactly one JSON line with these keys (the interface
other tools rely on; it never changes):

| Key                   | Meaning                                                                                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `session_id`          | `sessionId` of the first entry that has one, else the file name                                                                                                |
| `ts_last`             | ISO 8601 UTC of the last event                                                                                                                                 |
| `project`             | base name of the working directory, else of the transcript's folder                                                                                            |
| `turns`               | unique assistant `message.id` (one request spans several lines)                                                                                                |
| `human_prompts`       | user entries `classify_user_turn` calls `human`, minus interrupt markers                                                                                       |
| `compactions`         | compaction-summary entries                                                                                                                                     |
| `cost_usd`            | the harness's cost state if present (a drop in the running value is a reset; segments add), else per-message usage times the price table; `null` when unpriced |
| `context_tokens_peak` | max over assistant messages of input + cache-creation + cache-read tokens                                                                                      |
| `tool_errors`         | tool results flagged as errors                                                                                                                                 |
| `timer_turns`         | see metric 11                                                                                                                                                  |
| `outcome`             | `"pr-link"` when the session logged a PR link, else `null`; `outcomes.py` refines it                                                                           |

`metrics.py full` adds: `tool_calls`, `hook_blocks`, `hook_block_repeats`,
`hook_blocks_by_hook`, `gate_events`, `interrupts`, `denials`, `nudges`, `waits`,
`wait_seconds`, `wall_seconds`, `models`, `prs`, `skills_invoked`, `skills_offered`,
`skill_opportunities`, `fixed_tokens`, `cost_floor_usd`, `cost_source`, `unpriced`,
`timer_turns_big_context`, `ts_first`.

A session is **unpriced** when the cost state says an unknown model was used, when no cost state
exists and a model has no price, or when cost is 0 over more than 50 turns. Its `cost_usd` is
`null`; `cost_floor_usd` keeps the known part. Every cost sum below skips unpriced sessions.
The `<synthetic>` model id is not a priced model.

## The twelve

| #   | Metric                        | Formula                                                                                                                                                                                                                                                                                                 | Source                            |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 1   | Cost per human prompt         | sum(cost) / sum(human prompts) over priced sessions; companion: turns per prompt. Alert: week above the threshold, or any priced session above its own.                                                                                                                                                 | cost state or usage, user entries |
| 2   | Tool errors per 100 calls     | tool results with `is_error` / unique tool calls x 100; also per project. A denial is also an error. Alert only for projects with at least the minimum calls.                                                                                                                                           | message entries                   |
| 3   | Hook-block rate, repeat ratio | blocks per 100 calls, where a block is a hook event classified `deny`; repeat ratio = blocks repeating an earlier (hook name, text) pair in the same session / all blocks.                                                                                                                              | hook attachments                  |
| 4   | Gate integrity                | count of non-blocking hook events whose text starts `policy-gate: BLOCK`: a gate that says block and does not. Target 0.                                                                                                                                                                                | hook attachments                  |
| 5   | Human-correction rate         | (interrupts + permission denials + bare "continue" nudges) / human prompts x 100. Event types only; a wording regex is never part of it. A nudge is a prompt that is only continue, go on, keep going, carry on or proceed.                                                                             | user entries, tool results        |
| 6   | Human-wait time               | sum of gaps over 30 minutes between a session's last assistant entry and the next human prompt / session wall time; p50 and p90 of the per-session share. Alert: any single wait over 24 h (the report cannot tell whether work was still open).                                                        | timestamps                        |
| 7   | Always-loaded context         | fixed_tokens = characters of everything injected before the first assistant turn (instruction files, skill listing, tool list) / 4. fixed dollars = fixed_tokens x turns x cache-read price per token from the price table in `cost.py`.                                                                | entries before turn 1             |
| 8   | Skill dispatch hit rate       | invoked / opportunities per skill, split by whether the skill was listed with its description (`visible`) or by name only. An opportunity is a session where a human prompt matches the skill's regex in the `--dispatch` table and the skill was listed.                                               | listing, dispatch table           |
| 9   | Long-session share of spend   | cost of sessions with wall time over 24 h / total cost; also the cost share of sessions with 2 or more compactions (a stand-in for spend after the second one).                                                                                                                                         | wall time, compactions            |
| 10  | Compactions                   | per session and per $100; alert on any session at the threshold or a week total above it.                                                                                                                                                                                                               | compaction entries                |
| 11  | Timer-driven turns            | new assistant turns whose trigger is a task notification or the result of a timer tool (a wake-up, monitor or agent-list call), with no human input in between / all turns. The first new turn after a trigger counts once. `timer_turns_big_context` counts those in a context of 300K tokens or more. | tool names, notifications         |
| 12  | Unpriced spend                | count of unpriced sessions and their floor cost. Target 0.                                                                                                                                                                                                                                              | cost state                        |

Percentiles are nearest-rank. Shares are 0 to 1 in JSON and print as percent.

## North star: cost per merged PR

cost per merged PR = sum(cost of priced sessions touching at least one PR in the window) /
count(distinct `repo#number` PRs from those sessions whose state is MERGED, merged within 14 days
of the PR's last touching session). Repeated PR links are one PR. Also per project and as the
median cost per PR-session.

**Goodhart guard.** The number is printed only together with merged share (merged / distinct
PRs), median hours to merge and median review rounds (CHANGES_REQUESTED reviews). If any is
missing the report prints `withheld`. A cheap PR closed unmerged still counts as touched, so the
share is the honest companion. Alerts: a project-week with at least 5 PRs and cost per merged PR
above the threshold; merged share below the threshold.

PR states come from `outcomes.py`. Unknown, open and not-found PRs are not merged.

## Change log

`reflect/changes.jsonl`, one JSON object per accepted change:
`{"date": "2026-03-01", "rule": "R-gate", "metric": "m4", "baseline": 1}`. `metric` is `m1` to
`m12` or `north_star`. `report.py --changes FILE` prints the metric over sessions since `date`
next to the baseline. A change at least 14 days old whose metric moved by 5% of the baseline or
less is a **no-op candidate**: remove it or rework it.

## Deferred

Not built here: the ledger hook and statusline (proposals, the user wires them), scheduled runs,
a dashboard, an alerts inbox, and the skill-listing cap rate (the cap is not in the transcript).
The `--dispatch` table is an input the user supplies; no table ships.
