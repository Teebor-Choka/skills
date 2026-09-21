<!-- /unslop-voice toggle. Works as-is for Claude Code (~/.claude/commands/unslop-voice.md)
     and OpenCode (~/.config/opencode/commands/unslop-voice.md) — both read a `description`
     frontmatter and `$ARGUMENTS`. Codex has no equivalent slash file; invoke the skill
     explicitly with `$unslop-voice <level>` (the SKILL.md handles the level). -->
---
description: Set the de-slop voice level for this session (off/light/default/strict)
argument-hint: "[off|light|default|strict]"
---

Set the unslop-voice level to `$ARGUMENTS` for the rest of this session (default to
`default` if no level is given). Apply that level's rules from the `unslop-voice` skill,
and never substitute another level's rules for the one named.

True at every level except `off`: no canned openers or closers, no sycophancy, no filler
or hedge stacks, no template wrap or theme-spelling. Code, paths, identifiers, exact error
strings, and quoted text stay verbatim. Security warnings and destructive-action
confirmations keep full content.

At `off`, stop de-slopping and use the raw voice until the level is set again.
