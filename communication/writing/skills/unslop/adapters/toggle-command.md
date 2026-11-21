<!-- /unslop-mode toggle. Works as-is for Claude Code (~/.claude/commands/unslop-mode.md)
     and OpenCode (~/.config/opencode/commands/unslop-mode.md) — both read a `description`
     frontmatter and `$ARGUMENTS`. Codex has no equivalent slash file; invoke the skill
     explicitly with `$unslop <level>` (the SKILL.md handles the level). -->

---

description: Set the de-slop depth and/or length budget for this session
argument-hint: "[off|light|default|strict] [terse|normal|full]"
---

Set the unslop voice from `$ARGUMENTS` for the rest of this session. There are two independent
axes: de-slop depth (`off`, `light`, `default`, `strict`) and length budget (`terse`, `normal`,
`full`). Each argument names one axis; set the ones given and leave the other as it was. With no
argument, reset to depth `default`, budget `terse`. Apply the named level's rules from the
`unslop` skill, and never substitute another level's.

Depth controls which passes run: `light` is the surface pass only; `default` and `strict` add
the structural pass; `off` stops de-slopping (raw voice). Budget controls how much text:
`terse` is the shortest correct answer, lead with the result; `normal` cuts preamble and
scaffolding; `full` removes the length cap.

The floor holds at every setting except depth `off`: code, paths, identifiers, exact error
strings, and quoted text stay verbatim; security warnings and destructive-action confirmations
keep full content; brevity never drops a fact.
