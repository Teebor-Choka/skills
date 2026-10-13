# Platform: oh-my-pi (omp)

Docs: https://omp.sh (served from the repo `docs/` tree); repo https://github.com/can1357/oh-my-pi
(by Stencil Labs, a fork of Pi); npm `@oh-my-pi/pi-coding-agent`. The binary is **`omp`** (there
is no `pi` binary in this package). Docs track `main` with no versioned site and the project ships
very fast (680+ npm versions), so re-verify exact paths/keys against the installed build. Facts
below verified 2026-10-13 against the `docs/` sources linked at the end.

## Skill install locations (SKILL.md natively supported)

Non-recursive, one level under a `skills/` root; scanned by priority providers (higher wins,
first-wins dedup by skill name):

- `<cwd>/.omp/skills/<name>/SKILL.md` (project, native) and
  `~/.omp/agent/skills/<name>/SKILL.md` (user, native; profile-aware under
  `~/.omp/profiles/<p>/agent/`). Native scans **require `description`**.
- Compatibility providers — reads `.claude/skills` and `~/.claude/skills`, `.agent/skills` and
  `.agents/skills`, `.codex`, `.opencode`, `.github/skills/<name>/SKILL.md`, and portable Agent
  Plugins packages (root `plugin.json`, strict Agent Skills validation).

So the same checked-in `.claude/skills` or `.agents/skills` dir that serves Claude Code, Codex,
and OpenCode also serves omp — no omp-specific copy needed. Foreign _user_-level sources are
opt-in (`enabledProviders`); project-level foreign sources load by default. Custom roots via
`skills.customDirectories`.

Frontmatter (omp skill type): `name` (defaults to the directory name), `description`,
plus omp extras `globs`, `alwaysApply`, `hide`, `disable-model-invocation`, `enabled: false`.
Only `name` + `description` are portable; the extras are omp-specific (`hide` and `enabled` are
rejected by the strict `agent-plugins` provider), so keep them out of a portable core.

## Config and instruction files

- Config is **YAML**: user `~/.omp/agent/config.yml`, project `<cwd>/.omp/config.yml` (legacy
  `.omp/settings.json` still read). `omp config set|list|reset`. Profiles via `--profile`/
  `OMP_PROFILE`. Higher layers **replace** array settings rather than merging them.
- Always-on instruction files: native `~/.omp/agent/AGENTS.md` (user) and the nearest
  `.omp/AGENTS.md` (project), plus a sticky always-apply `RULES.md` (`.omp/RULES.md`,
  `~/.omp/agent/RULES.md`). It also reads standalone `AGENTS.md` (walks cwd→repo root) and
  `CLAUDE.md` as a fallback, and the Claude/Codex/OpenCode/Gemini/Copilot instruction files.
  `@path` imports expand inline (up to 5 hops). **`AGENTS.md` is the primary** file here. No
  documented size cap.

## Triggering

- **Auto** — name + description are injected into the system prompt; the model pulls the body on
  demand by reading the `skill://<name>` URI (progressive disclosure). Governed by `skills.enabled`,
  `skills.ignoredSkills`/`includeSkills` globs, `--skills <globs>`, `--no-skills`.
- **Explicit** — when `skills.enableSkillCommands` is true each skill registers `/skill:<name>
[args]` (namespaced `/skill:<ns>/<name>` on collision). Also usable mid-prompt as a token.
- **Commands** (human trigger) — markdown prompt files in `.omp/commands/*.md` (project) or
  `~/.omp/agent/commands/*.md` (user); it also reads `.claude/commands`, `.codex/commands`,
  `.opencode/commands`. Substitutions: `$1`, `$@[start:len]`, `$ARGUMENTS`, `$@`, Handlebars
  `{{args}}`; frontmatter `description`, `argument-hint`, `name`. Shell is not a command-level
  feature — the body carries a `bash` block the agent runs via the `bash` tool.

## Hooks and the native plugin system

- **Hooks** — JS/TS factories (`export default function hook(pi)` calling `pi.on(...)`) in
  `.omp/hooks/pre|post/*.{ts,js}` or `~/.omp/agent/hooks/pre|post/` (mirrors `.claude/hooks/
pre|post/`); `--hook <path>` aliases `--extension`. Events include `tool_call` (pre,
  fail-closed — a throwing handler blocks the tool), `tool_result` (post), the session/agent/turn
  lifecycle, and `before_subagent_spawn` (can block or reroute a spawn).
- **Extensions** — the native tool/command/provider API: a TS/JS module default-exporting
  `function(pi)` that calls `pi.registerTool`, `pi.registerCommand`, `pi.on`, `pi.registerFlag`,
  `pi.registerProvider`, etc. Discovery: `~/.omp/agent/extensions/*.{ts,js}`, `.omp/extensions/`,
  installed plugins under `~/.omp/plugins/node_modules`, `--extension`/`-e`, or the `extensions:`
  config array. `--no-extensions` disables ambient discovery; `--trusted-extension <abs>` allowlists.
- **Plugin packages + marketplace** — Claude-registry-compatible. A plugin dir bundles skills,
  commands, agents, rules, hooks, tools, MCP, LSP/DAP; its manifest is `package.json`
  `omp.extensions` or a portable root `plugin.json` (Agent Plugins 1.0.0). Marketplace catalog at
  `.omp-plugin/marketplace.json` (preferred) or `.claude-plugin/marketplace.json` (fallback).
  Manage with `/marketplace add|install|discover|list|update|uninstall` and `omp plugin
marketplace add/...`, `omp plugin install/uninstall/enable/disable`. Scopes: user and project
  (project shadows user). See `plugins.md` for the portable-manifest story.

## Subagents, parallel fan-out, MCP

- **Subagents** — markdown definitions in `.omp/agents/*.md` (project) / `~/.omp/agent/agents/*.md`
  (user); frontmatter `name`, `description`, body = `systemPrompt`, plus `tools`, `spawns`,
  `model`, `thinking`, `output` (JSON schema), `blocking`, `autoloadSkills`. Invoked via the
  `task` tool into isolated worktrees with parallel fan-out and IRC-style peer messaging; monitor
  via the Agent Hub (`Alt+A`); `wait` joins async agents. Nesting bound `task.maxRecursionDepth`
  (default 2). Bundled: `scout`, `reviewer`, `security-reviewer`, `task`, `sonic`. Note: it does
  NOT read `.claude/agents`/`.codex/agents` (different frontmatter contract) — a subagent adapter
  for omp is a separate file.
- **MCP** — full client (stdio/http/sse). `mcpServers` map in `.omp/mcp.json` (project) /
  `~/.omp/agent/mcp.json` (user); it also imports Claude, Codex, Gemini, OpenCode, Cursor, and
  VS Code MCP configs. `/mcp add` wizard; `/mcp enable|disable|reload|list`. The tool-name prefix
  as presented to the model is unverified from the docs (resources addressed as `mcp://` URIs).

## Headless / CI

```bash
omp -p "Use the <name> skill to …"                # print mode, last message to stdout
omp -p "/skill:<name> <args>" --approval-mode yolo # explicit skill, non-interactive
omp -p "…" --mode json --model opus                # NDJSON event stream
```

Key flags: `-p/--print`, `--mode text|json|rpc|acp`, `--model`/`--models`/`--thinking`,
`--approval-mode always-ask|write|yolo` (`--yolo`/`--auto-approve`), `--tools`/`--no-tools`,
`--skills`/`--no-skills`, `-e/--extension`, `--plugin-dir`, `--config`. Resume: `-c/--continue`,
`-r/--resume [id]`, `--fork`, and cross-harness `--from-claude`/`--from-codex`. There is no
documented dedicated "run this skill" flag — use `-p "/skill:<name> …"`.

Distinctive built-ins worth an adapter's awareness: `read` resolves `skill://`/`mcp://` URIs,
URLs, and GitHub PRs/issues; `debug` (DAP: lldb/dlv/debugpy), `lsp`, `ast_grep`/`ast_edit`,
`security_scan`, and `/review` (P0–P3 reviewer subagents with a ship/no-ship verdict).

## Minimal adapter set

The portable `SKILL.md` in `.claude/skills/<name>/` or `.agents/skills/<name>/` is already read
by omp — no omp copy needed. Add `.omp/commands/<name>.md` for a `/name` human trigger (or rely
on `/skill:<name>`), an `.omp/agents/<name>.md` only if the skill delegates to an omp subagent,
and a `.omp/hooks/pre|post/` factory only for a hard, event-driven gate.

## Sources (accessed 2026-10-13, raw on `main`)

skills `docs/skills.md`; context `docs/context-files.md`; commands
`docs/slash-command-internals.md`; hooks `docs/hooks.md`; extensions `docs/extensions.md`;
marketplace `docs/marketplace.md`; subagents `docs/task-agent-discovery.md`; MCP
`docs/mcp-config.md`; CLI `docs/cli-reference.md`; settings `docs/settings.md`. All under
`https://raw.githubusercontent.com/can1357/oh-my-pi/main/`.
