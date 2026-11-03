<!-- prose-craft always-on nudge, agent-neutral and deliberately thin.
     Paste into an agent's baseline instructions: AGENTS.md (Codex ~/.codex/AGENTS.md;
     OpenCode home/project AGENTS.md or opencode.json `instructions`) or CLAUDE.md (Claude
     Code). This is NOT a second always-on voice. Surface cleanup and AI-tell removal stay
     with the unslop skill; this only adds the above-the-sentence composition pass, and only
     when the writing is long enough to earn it. -->

## Composing prose: run the prose-craft pass

When you write anything longer than a short note (a doc, README, PR or issue body, report,
essay, or a multi-paragraph explanation), run the composition pass from the `prose-craft`
skill before you hand it over:

- **Structure and coherence first.** One point per paragraph, stated up front. Given
  information before new. A consistent topic string. Explicit connectives between sentences.
  No metadiscourse ("in this section", "it is worth noting").
- **Then sentence architecture.** A concrete actor as the subject with a strong verb. Kill
  nominalizations. Keep subject and verb close, heavy material at the end. Every pronoun
  resolves to one nearby antecedent.
- **Then concision.** Omit needless words; specific and concrete over abstract; cut qualifiers.

The full 20-item pass and its reasoning are in the skill's `references/`. These are strong
defaults, not gates: break one sooner than write something wooden.

Leave surface tells and "humanizing" to the `unslop` skill; do not duplicate that work here.
