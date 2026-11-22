# Running across agents

Paths in this file are relative to the skill directory.

One portable `SKILL.md` runs unchanged on Claude Code, Codex, and OpenCode. On-demand rewrites
need no adapter; the always-on voice needs a little per-agent wiring, with ready-to-copy
templates in `adapters/`.

Install the skill dir: Claude Code `~/.claude/skills/unslop/`; Codex `~/.agents/skills/unslop/`;
OpenCode `~/.config/opencode/skills/unslop/` (it also reads `.claude/skills` and `.agents/skills`,
so one dir serves all three).

Always-on baseline:

- Claude Code: `adapters/output-style.md` → `~/.claude/output-styles/unslop.md`, activated with
  `"outputStyle": "unslop"` in settings; `keep-coding-instructions: true` keeps coding behavior.
- Codex / OpenCode: paste `adapters/always-on.md` into the agent's `AGENTS.md` (Codex
  `~/.codex/AGENTS.md`; OpenCode home/project `AGENTS.md` or `opencode.json` `instructions`).

Toggle `/unslop-mode off|light|default|strict`:

- Claude Code: `adapters/toggle-command.md` → `~/.claude/commands/unslop-mode.md`.
- OpenCode: `adapters/toggle-command.md` → `~/.config/opencode/commands/unslop-mode.md`.
- Codex: invoke the skill explicitly with `$unslop <level>`.

For a large multi-document sweep, delegate one pass per file to subagents (see the
`model:extension-author` skill).
