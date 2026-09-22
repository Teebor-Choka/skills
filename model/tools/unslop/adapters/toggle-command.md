<!-- /unslop-mode toggle. Works as-is for Claude Code (~/.claude/commands/unslop-mode.md)
     and OpenCode (~/.config/opencode/commands/unslop-mode.md) — both read a `description`
     frontmatter and `$ARGUMENTS`. Codex has no equivalent slash file; invoke the skill
     explicitly with `$unslop <level>` (the SKILL.md handles the level). -->

---

description: Set the de-slop voice level for this session (off/light/default/strict)
argument-hint: "[off|light|default|strict]"
---

Set the unslop level to `$ARGUMENTS` for the rest of this session (default to `default` if
no level is given). Apply that level's rules from the `unslop` skill, and never substitute
another level's rules for the one named.

`light` runs the surface pass only; `default` and `strict` add the structural pass, so
which tells get cut depends on the level. The level-invariant floor holds at every level
except `off`: code, paths, identifiers, exact error strings, and quoted text stay verbatim,
and security warnings and destructive-action confirmations keep full content.

At `off`, stop de-slopping and use the raw voice until the level is set again.
