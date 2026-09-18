# Platform: OpenCode

Docs: https://opencode.ai/docs (config, agents, rules, skills, commands, plugins, cli). Repo
`github.com/sst/opencode` (now also under the `anomalyco` org); npm `opencode-ai`. Docs are
unversioned and a parallel `/v2/docs/` set exists — verify load-bearing details live.

## Skill install locations (SKILL.md natively supported)

Searched (walks up to the git worktree root for project paths):

- `.opencode/skills/<name>/SKILL.md` (project)
- `~/.config/opencode/skills/<name>/SKILL.md` (global)
- `.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md` (compatibility)

Because OpenCode also reads `.claude/skills` and `.agents/skills`, one checked-in skill dir can
serve Claude Code, Codex, and OpenCode at once. Frontmatter: `name` (matches dir,
`^[a-z0-9][a-z0-9-]*$`, 1–64), `description` (1–1024), optional `license`, `compatibility`,
`metadata`.

## Triggering

- **Auto** — skills are listed inside the built-in `skill` tool's description; the model loads
  a body on demand with `skill({ name: "<name>" })` (progressive disclosure). Governed by the
  `skill` permission key (`allow|ask|deny`, wildcards, per-agent override).
- **Commands** (human trigger) — `.opencode/commands/<name>.md` (or the `command` key), invoked
  `/<name>`. Frontmatter: `description`, `agent`, `model`, `subtask`. Body substitutions:
  `$ARGUMENTS`, `$1`, `` !`cmd` `` shell injection, `@file` inclusion:
  ```markdown
  ---
  description: Draft release notes for a range
  agent: build
  subtask: true
  ---

  Commits: !`git log --oneline $1..HEAD`
  Use the release-notes skill to draft notes and a version bump.
  ```
- **Plugins / hooks** — JS/TS in `.opencode/plugins/` (or the `plugin` key) return a hooks
  object: `tool.execute.before/after`, `file.edited`, session/message events. Throwing in a
  `before` hook blocks the tool:
  ```javascript
  export const Guard = async ({ $ }) => ({
    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash" && /rm -rf/.test(output.args.command))
        throw new Error("blocked");
    },
  });
  ```
  (Historically MCP tool calls did not fire plugin hooks — verify.)

## Config and rules

`opencode.json` / `opencode.jsonc` (add `"$schema": "https://opencode.ai/config.json"`),
merged global→project→`.opencode/`. `AGENTS.md` is the always-on rules file (falls back to
`CLAUDE.md`); the `instructions` key pulls in extra rule files by path/glob.

## Agents (personas) vs skills (knowledge)

A **skill** is on-demand instructions surfaced through the shared `skill` tool (no own model or
tools). An **agent/mode** is a persona with its own model, prompt, and permissions; agents use
skills. Define agents in `.opencode/agents/<name>.md` (filename = name) or the `agent` key:

```markdown
---
description: Reviews code for quality and best practices
mode: subagent # primary | subagent | all
model: anthropic/claude-sonnet-4-5
permission: { edit: deny, bash: deny }
---

You are a code reviewer. Focus on quality, bugs, and edge cases.
```

Subagents run via auto-delegation, `@name`, or the `task` tool; `subagent_depth` (default 1)
bounds nesting. Permissions use `allow|ask|deny` with wildcards over keys like `read, edit,
bash, task, webfetch, skill`.

## Advanced workflows and MCP

A primary agent (Build) delegates to narrow subagents (Plan/read-only, review/no-edit,
Scout/research); permissions enforce boundaries. MCP servers under the `mcp` key
(`opencode mcp add`). Plugins add deterministic guardrails and side effects around the loop.

## Headless / CI: `opencode run`

```bash
opencode run --auto -q --agent build -m anthropic/claude-sonnet-4-5 "Use the <name> skill to …"
opencode run "summarize this diff" --file diff.patch -f json
opencode serve   # persistent server (default :4096); then: opencode run --attach http://localhost:4096 "…"
```

Resume with `-c/--continue` or `-s/--session`. Verify flag spellings live (`-f` overloads
`--file`/`--format` across builds).

## Minimal adapter set

Portable `SKILL.md` in `.opencode/skills/<name>/` (or reuse the `.claude/skills` copy). Add
`.opencode/commands/<name>.md` for a `/name` human trigger, an `agent` to fix model/permissions
for CI, and a plugin only for a hard guardrail.
