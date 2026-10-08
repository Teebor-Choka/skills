# Instruction files across agents

Which always-on instruction file each agent reads, so one repo can serve all of them. Skills are the
on-demand layer (see the per-agent files in `platforms/`); this is the always-loaded layer. Verified
against the linked docs on 2026-10-07; agents change this often, so re-check before relying on an edge case.

| Agent          | Files discovered                                                                                                                                                 | Resolution                                                                                                           | Source                                                                                                                          |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Claude Code    | `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` in the working dir and every parent; `~/.claude/CLAUDE.md`; `.claude/rules/*.md`                             | All concatenated, root first. Subdirectory files load on demand. `AGENTS.md` is read only if no `CLAUDE.md` is found | [memory](https://code.claude.com/docs/en/memory)                                                                                |
| Codex          | `~/.codex/AGENTS.override.md` or `AGENTS.md`; per directory from git root down to the working dir: `AGENTS.override.md`, `AGENTS.md`, fallback names             | One file per directory, concatenated root down, so the closest wins. Capped by `project_doc_max_bytes` (32 KiB)      | [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md)                                                         |
| OpenCode       | `AGENTS.md` or `CLAUDE.md` searched upward from the working dir; `~/.config/opencode/AGENTS.md`; `~/.claude/CLAUDE.md`                                           | First match wins per category; `AGENTS.md` beats `CLAUDE.md`. `instructions` in `opencode.json` adds paths or globs  | [rules](https://opencode.ai/docs/rules/)                                                                                        |
| GitHub Copilot | `.github/copilot-instructions.md`; `.github/instructions/*.instructions.md` with `applyTo` globs; `AGENTS.md` anywhere, or `CLAUDE.md` / `GEMINI.md` at the root | Repo-wide and path-specific files combine; for agent files the nearest `AGENTS.md` wins                              | [repository instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions) |

## Writing one file that all four read

- Put shared conventions in `AGENTS.md`. Codex, OpenCode, and Copilot read it directly.
- Claude Code reads `AGENTS.md` natively from v2.1.277, but only when no `CLAUDE.md` or
  `CLAUDE.local.md` exists in the working dir or above. Adding either one hides `AGENTS.md`.
  Two fixes: a `CLAUDE.md` whose body is `@AGENTS.md` (imports expand at launch, four hops deep), or
  setting Project instructions to `claude-md-and-agents-md` in `/config`. Use the import for older
  versions and for sessions where native `AGENTS.md` support is off.
- Keep Claude-only rules in `CLAUDE.md` below the import, Copilot path rules in
  `.github/instructions/`, and Codex-only overrides in `AGENTS.override.md` (local, uncommitted).
- Stay under Codex's 32 KiB combined cap; nested `AGENTS.md` files count toward it.
- Quality review of a `CLAUDE.md` (what to include, how to trim) is covered by the
  `claude-md-management` plugin and `references/auditing.md`, not here.
