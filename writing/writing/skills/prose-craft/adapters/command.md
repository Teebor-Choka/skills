<!-- /prose-craft invoke command. Works as-is for Claude Code
     (~/.claude/commands/prose-craft.md) and OpenCode
     (~/.config/opencode/commands/prose-craft.md): both read a `description` frontmatter
     and $ARGUMENTS. Codex has no equivalent slash file; invoke the skill by name instead. -->

---

description: Compose or revise prose for clarity and concision (prose-craft skill)
argument-hint: "[compose|review|voice] <text or file>"
---

Apply the `prose-craft` skill to `$ARGUMENTS`.

- Default mode is **compose or revise**: return the improved prose.
- If the first argument is `review`, run in **review** mode instead: report findings as a
  terse `location → rule → fix` list and change nothing.
- If the first argument is `voice`, run **voice matching** on top of the craft pass: follow
  `references/voice-matching.md`. It needs a 300+ word sample of the user's own writing; if
  none is supplied, ask for one rather than guessing a voice.

Run the pass from the skill's `references/checklist.md` in order: structure and coherence,
then sentence architecture, then word-level concision. Do not change any fact, number, quote,
or citation. For removing AI tells or "humanizing" machine text, use the `unslop` skill, not
this one.
