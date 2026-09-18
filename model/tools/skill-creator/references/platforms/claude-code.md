# Platform: Claude Code

Docs: https://code.claude.com/docs (skills, sub-agents, hooks, agents, mcp). Verify against
the installed version — these move.

## Skill install locations

- `~/.claude/skills/<name>/SKILL.md` — personal (all projects)
- `.claude/skills/<name>/SKILL.md` — project (commit to the repo)
- nested `.../.claude/skills/` — scoped to that subtree
- `<plugin>/skills/` — plugin scope; plugins are listed in `.claude-plugin/marketplace.json`

## Frontmatter (portable + Claude-only extras)

Portable: `name`, `description` (+ optional `license`, `compatibility`, `metadata`).
Claude-only extras — keep these in the Claude adapter, not the portable core:

| Key                                    | Effect                                            |
| -------------------------------------- | ------------------------------------------------- |
| `disable-model-invocation: true`       | only the user's `/name` runs it (no auto-trigger) |
| `user-invocable: false`                | only the model runs it                            |
| `allowed-tools` / `disallowed-tools`   | pre-approve / deny tools for the skill's turn     |
| `context: fork`, `agent`, `background` | run the skill inside an isolated subagent         |
| `model`, `effort`                      | override session model / effort                   |
| `paths: "src/**/*.py"`                 | auto-trigger on matching file context             |
| `arguments: [a, b]`                    | named positional args for `/name a b`             |

## Triggering

- **Auto** — from `description` (unless `disable-model-invocation`).
- **Explicit** — `/skill-name`, `/skill-name arg1 arg2`, `/scope:name` in a monorepo.
- **Command adapter** — `.claude/commands/<name>.md` (frontmatter `name`, `description`);
  invoked as `/<name>`. Supports `$ARGUMENTS`, `$0/$1`, `${CLAUDE_PROJECT_DIR}`,
  `${CLAUDE_SKILL_DIR}`, and `` !`cmd` `` inline shell (needs tool permission; 2-min timeout).
- **Hooks** — `hooks` in `settings.json`:
  ```json
  {
    "hooks": {
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            {
              "type": "command",
              "command": ".claude/hooks/check.sh",
              "timeout": 60
            }
          ]
        }
      ]
    }
  }
  ```
  Events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart/End`,
  `FileChanged`, `SubagentStart/Stop`. A command hook exiting non-zero blocks the action.
- **Disable/limit** — `skillOverrides` in `settings.json` (`"name": "off" | "name-only"`).

## Advanced workflows

- **Subagents** — `.claude/agents/<name>.md` (frontmatter: `name`, `description`, `tools`,
  `model`, `permissionMode`, `skills`, `mcpServers`, `isolation: worktree`). Invoke in prose,
  guarantee with `@"name (agent)"`, or via the Agent tool. Parallel = several Agent calls in
  one turn.
- **Workflow tool** — deterministic JS orchestration (`agent()`, `parallel()`, `pipeline()`)
  for fan-out/verify/synthesize. Claude-specific; keep out of the portable body.
- **MCP** — `mcpServers` in `settings.json` or per-subagent; tools are `mcp__<server>__<tool>`.

## Headless / CI

```bash
claude -p "Use the <name> skill to …"
```

## Minimal adapter set

For a skill that should also have a guaranteed human entry and a CI gate: keep the portable
`SKILL.md` in `.claude/skills/<name>/`, add `.claude/commands/<name>.md` (one line: "use the
`<name>` skill with $ARGUMENTS"), and a `PreToolUse`/`FileChanged` hook only if you need a
deterministic gate.
