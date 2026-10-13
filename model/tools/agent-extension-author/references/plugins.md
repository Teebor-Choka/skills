# Native plugins across agents

A **skill** is one capability. A **plugin** is a distribution unit: a directory that bundles
skills, subagent definitions, hooks, commands, and MCP servers, installed and updated as one
thing from a marketplace. Ship a plugin when a skill travels with its adapters (a command, a
hook-backed gate, a subagent, an MCP dependency) and you want teammates to install the whole
set with one command and get versioned updates — not when a lone `SKILL.md` in
`~/.<agent>/skills/` already does the job. Verified against the linked docs on 2026-10-13;
plugin systems are new and moving fast, so re-check before relying on an edge case.

## The portable core: the Agent Plugins standard

Just as all four agents read the same open **Agent Skills** standard (`SKILL.md`), plugins now
have an open, vendor-neutral standard — **Agent Plugins** (`agent-plugins.org`, spec at
`github.com/agentplugins/agent-plugins-spec`; TSC: Amazon, Cursor, Microsoft, OpenAI, Vercel).
It defines a portable plugin container for Agent Skills + MCP servers, with reverse-domain
**extension namespaces** so each client adds its own behavior without touching the portable
core. Author the portable core once; add a thin vendor overlay only where an agent needs it.

```
my-plugin/
├── plugin.json          # portable manifest (Agent Plugins schema)
├── skills/<name>/SKILL.md   # the portable skills (same dirs the skill core ships)
├── mcp.json             # portable MCP server declarations (optional)
├── assets/              # icons / branding (optional)
└── extensions/          # or reverse-domain overlays — vendor-specific, see below
```

Portable `plugin.json` (confirmed fields; consult the schema for the full set):

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What the bundle adds and when to reach for it"
}
```

Portable `mcp.json`:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "my-server": { "type": "streamable-http", "url": "https://example.com/mcp" }
  }
}
```

Keep every vendor-specific key under its reverse-domain namespace (`extensions.com.openai`,
`com.example.client/…`) or a client compatibility manifest, with paths relative to the plugin
root and starting `./`. That is what keeps the plugin installable on more than one agent.

## Per-agent native plugin mechanisms

| Agent       | Manifest / overlay                                                                  | Marketplace catalog                                                              | Install / manage                                                                          |
| ----------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Claude Code | `.claude-plugin/plugin.json`                                                        | `.claude-plugin/marketplace.json`                                                | `/plugin`; `claude plugin …`; `--plugin-dir`                                              |
| Codex       | root `plugin.json` + `extensions.com.openai` (+ `.codex-plugin/plugin.json` compat) | `.agents/plugins/marketplace.json` (repo) · `~/.agents/plugins/marketplace.json` | `codex plugin marketplace add owner/repo`; `codex plugin marketplace list/upgrade/remove` |
| OpenCode    | no plugin-bundle format; plugins are JS/TS modules                                  | —                                                                                | `.opencode/plugins/*.{js,ts}` or the `plugin` key / npm package                           |
| oh-my-pi    | see `platforms/oh-my-pi.md`                                                         | see `platforms/oh-my-pi.md`                                                      | see `platforms/oh-my-pi.md`                                                               |

### Claude Code

A plugin is a directory with a `.claude-plugin/plugin.json` manifest (`name`, optional
`version`, `description`, metadata) holding any of: `skills/<name>/SKILL.md`, `agents/<name>.md`,
`hooks/hooks.json`, `.mcp.json`, and commands. A skill inside a plugin runs as
`/<plugin>:<skill>`. A plugin whose hooks are a JavaScript module (that can also draw panes and
add commands) is a **mod** (`plugins/mods/`). Distribute via a marketplace: a repo with
`.claude-plugin/marketplace.json` listing each plugin and where to fetch it; users
`/plugin marketplace add` it, then install by name (`my-plugin@my-marketplace`). Scopes: user,
project (committed `.claude/settings.json`), local. Disk cache: `~/.claude/plugins/`. Develop
without a marketplace via `--plugin-dir`. Docs: https://code.claude.com/docs/en/plugins (and
`/plugins/components`, `/plugins/create`, `/plugins/manifest-reference`).

### Codex

Codex adopted the portable Agent Plugins format: keep `plugin.json`, `mcp.json`, and `skills/`
at the plugin root, put OpenAI-specific metadata under `extensions.com.openai` in `plugin.json`
(keys seen: `apps` → an `.app.json` of MCP mappings, `hooks`, `onboardingSkill`, `interface`
for display name/icons/category), and an optional `.codex-plugin/plugin.json` compat overlay.
Lifecycle hooks live in `hooks/hooks.json` but are desktop-only and bar a plugin from the public
directory. Marketplaces are git repos or local dirs with `marketplace.json` at
`$REPO_ROOT/.agents/plugins/` or `~/.agents/plugins/`:

```bash
codex plugin marketplace add owner/repo [--ref main] [--sparse .agents/plugins]
codex plugin marketplace list | upgrade [name] | remove <name>
```

Admins govern availability (pre-installed / available / blocked) through JSON policy files.
Self-serve publishing to the official directory was "coming soon" as of mid-2026 — verify.
Docs: https://developers.openai.com/plugins/build/plugins.

### OpenCode

OpenCode has no plugin-_bundle_ format in the Agent Plugins sense; its native extension point is
a **plugin = a JS/TS module** in `.opencode/plugins/` (or the `plugin` key, or an npm package)
that returns a hooks object (`tool.execute.before/after`, `file.edited`, session/message
events). That is the deterministic-guardrail mechanism, not a skills+MCP distribution package.
To distribute a skill set to OpenCode, check the skill dir into `.claude/skills` or
`.agents/skills` (both of which OpenCode reads) and ship any guardrail as a plugin module. See
`platforms/opencode.md`.

## When to package as a plugin (and which one)

- **One capability, no adapters** → a standalone `SKILL.md`, not a plugin. Simpler to install
  and nothing to version.
- **A skill plus its command / hook / subagent / MCP, distributed to a team** → a plugin.
  Author the portable core (`plugin.json` + `skills/` + `mcp.json`), then add only the vendor
  overlays for the agents you target.
- **A hard, event-driven guardrail with no skill** → on Claude Code a hooks `mod`, on OpenCode a
  plugin module; both are code, not a portable bundle. Keep the logic in a shared script the
  overlay calls (same portability trick as hooks in `triggering.md`).
- **Many skills shipped together** → a plugin is the right unit on Claude Code and Codex;
  OpenCode consumes the bundled `skills/` dir directly and takes guardrails as plugin modules.

Lint the portable manifest with `scripts/validate_plugin.py <plugin-dir>`.
