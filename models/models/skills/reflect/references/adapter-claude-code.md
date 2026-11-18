# Adapter: Claude Code transcripts

The only place the core skill depends on one harness. The code is the ADAPTER section of
`reflectlib.py` (`iter_entries`, `entry_time`, `message_of`, `collect_files`) plus the
field names listed here. A port to another harness replaces those functions and this file.

## Where sessions live

`~/.claude/projects/<cwd-slug>/<uuid>.jsonl` (the slug is the working directory with `/`
rewritten to `-`). The subagents of a session are in `<uuid>/subagents/agent-<id>.jsonl`,
each with `agent-<id>.meta.json` (`agentType`, `description`, `finished`). Pass the project
folder, or the session file and its folder: the scan joins them into one run.

## Fields the scripts read

| Need                        | Field                                                                                                                                                                                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Event time (windows, trend) | `timestamp` on each entry; an entry without one takes the previous entry's                                                                                                                                             |
| Turn                        | `message.id` of `type: assistant` entries (one request spans several lines)                                                                                                                                            |
| Tool call, once per id      | `message.content[]` blocks with `type: tool_use` and `id`                                                                                                                                                              |
| Human versus injected       | `isMeta`, `isCompactSummary`, `sourceToolUseID`, `origin.kind`, text markers such as `<system-reminder>`, `<command-name>`, `<task-notification>`, `<cross-session-message>`, a `Base directory for this skill` prefix |
| Queued human message        | `type: attachment`, `attachment.type: queued_command`, `attachment.prompt`                                                                                                                                             |
| Hook events                 | `type: attachment`, `attachment.type` of `hook_blocking_error`, `hook_non_blocking_error`, `hook_additional_context`, `hook_success`, with `hookName`, `exitCode`                                                      |
| Skill listing               | `attachment.type: skill_listing`, `attachment.content`: one `- name: description` per line; `name` is `plugin:skill` for a bundle                                                                                      |
| Tools offered               | `type: system`, `subtype: init`, `tools`                                                                                                                                                                               |
| Artifact produced           | `type: pr-link` entries                                                                                                                                                                                                |
| Subagent cost               | `<task-notification>` blocks in the parent (id, status, usage)                                                                                                                                                         |
| Dollar cost                 | `message.usage` and `message.model` per assistant entry; optional `type: cost-state` entries with `totalCostUsd`                                                                                                       |

Not verified against every Claude Code version: the hook attachment names, the
`skill_listing` and `init` shapes, and the `cost-state` entry. A script that finds none of
them reports empty or null results (for example `tools_never_called: null`), never a guess.
Check one real transcript with `drill.py` before trusting a null.

## Fields the metrics read

Names live in the ADAPTER section of `reflectlib.py`; another harness redefines them.

- `pr-link` entries: `prRepository` and `prNumber` (the PR is `repository#number`).
- `cost-state`: `totalCostUsd` or `totalCostUSD`, and `hasUnknownModelCost`.
- Timer tools (a call whose later result or notification wakes the agent): `ScheduleWakeup`,
  `Monitor`, `ListAgents`. Skill tool: `Skill`, with `input.skill`.
- Interrupt: a user entry whose text starts `[Request interrupted by user`. Permission denial: an
  error tool result containing `The user doesn't want to proceed with this tool use`.
- Hook text: the first non-empty of `stderr`, `content`, `stdout`, `output`, `text` on the hook
  attachment. Skill listings come in several `skill_listing` attachments; merge them.
- A session's id is `sessionId`; its project is the base name of `cwd`.

## Not provided

An adapter that turns cross-session messages, `SendMessage` calls and issue label events
into a coordination log (RF-13) does not exist yet. Pass an orchestrator log with
`--coordination` when one exists.
