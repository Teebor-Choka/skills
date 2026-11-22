# Modes, levels, and length budget

Paths in this file are relative to the skill directory.

Two ways to use this skill:

- **On demand** — rewrite a specific target text (when asked to "unslop this"). Run the
  full process below.
- **Always-on voice** — keep everything _you_ emit de-slopped by default, every response,
  session-wide. Wire it with the output style or `AGENTS.md` baseline in `adapters/`, and
  adjust per session with `/unslop-mode off|light|default|strict` for de-slop depth and
  `/unslop-mode terse|normal|full` for length (Codex: `$unslop <level>`).
  This includes the prose inside a skill's or plugin's frontmatter — the `description` a user
  and the triggering model actually read is in scope, so the no-em-dash and no-"serves as" rules
  apply to it (they are a common offender). De-slop the description text; leave the YAML keys,
  `name`, and structure alone, since those are config, not prose.

The level dials how much of the process runs; the default is **default**:

| Level       | Runs                                                                         |
| ----------- | ---------------------------------------------------------------------------- |
| **off**     | Nothing. Raw voice.                                                          |
| **light**   | Surface pass only; structure untouched.                                      |
| **default** | Surface + structural pass. The standing everyday level.                      |
| **strict**  | Surface + structural, applied hard and to short replies too; terse register. |

At every level except `off`, keep full content for security warnings, destructive-action
confirmations, exact errors, and quoted text — clarity wins over brevity.

### Length budget

A second, independent axis sets how much text to produce, regardless of de-slop level. The
default is **terse**. The de-slop level fixes _how_ you write; the budget fixes _how much_.

| Budget     | Produces                                                                                                                                       |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **terse**  | Shortest answer that stays correct and complete. Lead with the outcome; a few sentences for routine work, expand only where the task needs it. |
| **normal** | Answer or result first; no preamble or summary wrap; headings and lists only when they carry real structure.                                   |
| **full**   | No length cap. Say everything the task needs.                                                                                                  |

The budget caps volume, never content. The no-over-compression rule holds at every budget:
whole sentences, no dropped articles, fragments, or symbol-speak — slightly more terse than
full prose, never caveman. Facts, caveats, exact strings, and security or destructive-action
confirmations stay complete; precedence is facts > brevity.

Set either axis with `/unslop-mode <depth|budget>` (e.g. `/unslop-mode terse`, `/unslop-mode
light`); naming one axis leaves the other unchanged.
