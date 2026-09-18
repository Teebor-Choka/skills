# Programmatic triggering across agents

A skill can fire four ways. The first is model-driven (the description); the rest are
deterministic and live in per-agent adapters. Pick the least machinery that does the job.

| Mechanism                     | Claude Code                            | Codex                            | OpenCode                                          |
| ----------------------------- | -------------------------------------- | -------------------------------- | ------------------------------------------------- |
| Auto-trigger by `description` | yes (implicit)                         | yes (implicit, ~2% context cap)  | yes (via the `skill` tool)                        |
| Explicit invocation           | `/skill-name`                          | `$skill-name` (CLI)              | model calls `skill({name})`; humans use a command |
| Named command                 | `.claude/commands/<name>.md` → `/name` | `~/.codex/prompts/*.md` (legacy) | `.opencode/commands/<name>.md` → `/name`          |
| Lifecycle hooks               | `settings.json` `hooks` (events)       | `[hooks.*]` in `config.toml`     | plugins in `.opencode/plugins/` (event hooks)     |
| Headless / CI                 | `claude -p "…"`                        | `codex exec …`                   | `opencode run …`                                  |

## 1. Description auto-trigger (all three)

The default and most portable path — no adapter, just a good `description` (see
`authoring.md`). All three read only `name` + `description` up front and load the body when a
task matches. Note: simple one-step requests may not trigger any skill on any agent because
the model just does them directly; write the description for substantive, multi-step tasks.

## 2. Explicit and command triggers (deterministic human entry)

When a human wants a guaranteed entry point, add a command adapter per agent. Commands can
inject arguments and live shell output, which makes them deterministic:

- **Claude Code** — `.claude/commands/<name>.md`; invoke `/<name> arg1 arg2`. Body supports
  `$ARGUMENTS`, `$1`, and `` !`cmd` `` context injection.
- **OpenCode** — `.opencode/commands/<name>.md` with frontmatter (`agent`, `subtask`,
  `model`); invoke `/<name>`; same `$ARGUMENTS`/`$1`, `` !`cmd` ``, `@file` substitutions.
- **Codex** — a real skill is invoked explicitly with `$skill-name`; the older
  `~/.codex/prompts/*.md` (`/prompts:<name>`) still works but is legacy.

A command usually just says "use the `<name>` skill with these inputs", so the know-how stays
in the portable SKILL.md and the command is a thin trigger.

## 3. Lifecycle hooks (deterministic, event-driven)

Hooks fire the skill (or a guard) on events, not on model choice. Use them for policy gates
and "run X after Y" automation.

- **Claude Code** — `hooks` in `settings.json`. Events: `PreToolUse`, `PostToolUse`,
  `UserPromptSubmit`, `Stop`, `SessionStart/End`, `FileChanged`, `SubagentStart/Stop`.
  A `matcher` filters by tool name or regex; hook types include command, prompt, MCP-tool,
  and agent. A command hook that exits non-zero can block the action.
- **Codex** — `[[hooks.PreToolUse]]` (and other lifecycle points) in `config.toml`, running
  an external command with a `matcher` and `timeout`. Admins can force
  `allow_managed_hooks_only = true`.
- **OpenCode** — JS/TS plugins in `.opencode/plugins/` return a hooks object:
  `tool.execute.before/after`, `file.edited`, session/message events. Throwing in a
  `before` hook blocks the tool.

Hooks are the portability weak point: each agent's event names and payloads differ. Keep hook
logic in a small script the hook calls, so the same script backs all three and only the
wiring differs.

## 4. Headless / CI (deterministic, scriptable)

Run a skill from a pipeline or pre-commit with no TUI:

```bash
# Claude Code
claude -p "Use the <name> skill to …"

# Codex (JSON stream, pinned profile, capture final message)
codex exec --json -p ci --sandbox workspace-write -o out.txt "\$<name> …"

# OpenCode (quiet, auto-approve non-denied permissions, pick agent/model)
opencode run --auto -q --agent build -m anthropic/claude-sonnet-4-5 "Use the <name> skill to …"
```

Chain steps by parsing JSON output into the next call, or keep state with session resume
(`codex exec resume`, `opencode run --continue/--session`, `opencode serve --attach`).

## Choosing

- Reusable know-how a model should reach for on its own → description only (portable).
- A human wants a one-key entry → add a command adapter.
- "Always run/allow/deny on event X" → a hook (or an OpenCode plugin), backed by a shared
  script.
- Runs in CI/pre-commit → the headless entry point, usually pinned to a profile/agent for
  determinism.

Per-agent file formats and exact fields: `platforms/claude-code.md`, `platforms/codex.md`,
`platforms/opencode.md`.
