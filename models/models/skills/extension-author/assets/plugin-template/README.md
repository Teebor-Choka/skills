# Portable plugin template

Starter for a native plugin bundle built on the open **Agent Plugins** standard
(`agent-plugins.org`), the portable layer under Claude Code, Codex, OpenCode, and oh-my-pi
plugin systems. See `references/plugins.md` for the full story and per-agent overlays.

Fill in and lay out as:

```
my-plugin/
├── plugin.json          # this file, renamed/edited (portable manifest)
├── mcp.json             # optional, only if the bundle ships MCP servers
├── skills/<name>/SKILL.md   # one dir per bundled skill (a portable skill core)
├── agents/<name>.md     # optional subagent definitions
├── commands/<name>.md   # optional slash commands
├── hooks/               # optional, event hooks (per-agent; keep logic in a shared script)
└── assets/              # optional icons/branding
```

`marketplace.json` is the catalog you publish separately (a repo listing one or more plugins);
it does not live inside the plugin dir.

Per-agent overlays, when needed (keep the portable core above untouched):

- Claude Code: `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`.
- Codex: OpenAI keys under `extensions.com.openai` in `plugin.json`; marketplace at
  `.agents/plugins/marketplace.json`.
- oh-my-pi: `package.json` `omp.extensions` or the portable `plugin.json`; marketplace at
  `.omp-plugin/marketplace.json` (or the Claude-compatible `.claude-plugin/marketplace.json`).
- OpenCode: no bundle format; ship the `skills/` dir via `.claude/skills`/`.agents/skills` and
  any guardrail as an `.opencode/plugins/` module.

Lint with `scripts/validate_plugin.py <this-dir>`.
