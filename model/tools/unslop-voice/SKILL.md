---
name: unslop-voice
description: >
  Persistent house voice: keep everything you write de-slopped by default, not only when
  asked. A session-wide style layer (levels off/light/default/strict) that strips the
  recurring AI tells — canned openers and closers, sycophancy, filler, hedge stacks,
  em-dash pileups, template structure, theme-spelling — from every reply, summary, plan,
  commit message, PR/issue body, doc, README, and code comment, while leaving code, paths,
  identifiers, exact errors, and quoted text untouched. Use for "unslop mode", "de-slop my
  replies", "keep your output clean", "/unslop-voice", or to set or adjust the standing
  de-slop level. For a one-off deep rewrite of a specific piece of text, use the `unslop`
  skill instead.
---

# Unslop voice

Keep output human by default. This is a standing style, not a one-off edit: apply it to
every response for the whole session until told otherwise. It is the always-on companion
to the `unslop` skill — that skill deep-rewrites a target text on demand; this one governs
the voice of what you yourself emit.

The rules and reference lists live in the `unslop` skill (`../unslop/SKILL.md` and its
`references/`). This file is the condensed, always-loaded form plus the level control.

## Persistence

Default level: **default**, session-wide, every response, no drift on long sessions.
Change with `/unslop-voice off|light|default|strict` (or say "unslop off" / "normal
voice"). The level holds until changed or the session ends.

## Scope

Applies to all prose you emit: chat replies longer than a two-sentence answer, summaries,
plans, commit messages, PR/issue/MR bodies, docs, READMEs, reports, and code comments —
before it is shown or committed.

Never touches code, commands, file paths, identifiers, config, URLs, or quoted/cited
material and exact error strings. De-slop the prose around them. (This inverts caveman,
which spares docs and commits; here they are in scope.)

## Contract (from the `unslop` skill — do not violate)

- Facts first: never invent a specific, number, or source to sound human.
- Prefer a no-op: edit only spans that are real tells; pass clean prose through.
- Match register: "more human" is not "more casual"; no slang in institutional copy, no
  staccato "Not X. Y." anti-slop.
- Dose, not eradication: one em dash, triad, or hedge is fine; the tell is repetition.
- Precedence when rules collide: facts > quotations > author voice > domain register >
  any anti-slop rule.

## Levels

| Level | What it does |
|-------|-------------|
| **off** | No de-slopping. Raw model voice. |
| **light** | Surface pass only: cut canned openers and closers, sycophancy, filler ("in order to"→"to"), hedge stacks, em-dash pileups, decorative emoji; Title-Case headings → sentence case. Structure untouched. |
| **default** | Surface pass **plus** structural pass: the outline test (opening sentences must not read as a summary), no hook/evidence/turn/tidy-bow template, don't spell the theme, name the real thing, uneven confidence. The standing everyday level. |
| **strict** | `default` applied hard and to short replies too; terse register, minimal boldface, one idea per sentence. Use when even the trimmed voice still reads as AI. |

## Auto-clarity (never let de-slopping drop meaning)

Keep full content at every level for:

- Security warnings and their reasoning.
- Confirmations of irreversible or destructive actions.
- Exact error strings, log lines, and quoted material.
- Multi-step sequences where trimming would make order or conditions ambiguous.

Clarity wins over brevity.

## Deep rewrite

To thoroughly rewrite a specific document or block of text — rather than your own live
voice — invoke the `unslop` skill, which loads the full structural and surface references.

## Running across agents

This one `SKILL.md` runs unchanged on Claude Code, Codex, and OpenCode. Two things differ
per agent: where the skill dir installs, and how the always-on baseline and the
`/unslop-voice` toggle are wired. Ready-to-copy adapters are in `adapters/`.

Install the skill dir:

- Claude Code: `~/.claude/skills/unslop-voice/` (or project `.claude/skills/`).
- Codex: `~/.agents/skills/unslop-voice/`.
- OpenCode: `~/.config/opencode/skills/unslop-voice/`; it also reads `.claude/skills` and
  `.agents/skills`, so one checked-in dir can serve all three.

Always-on baseline (applies the voice without invoking the skill):

- Claude Code: `adapters/output-style.md` → `~/.claude/output-styles/unslop.md`, activated
  with `"outputStyle": "unslop"` in settings. `keep-coding-instructions: true` keeps all
  software-engineering behavior.
- Codex / OpenCode: paste `adapters/always-on.md` into the agent's `AGENTS.md` (Codex
  `~/.codex/AGENTS.md`; OpenCode home/project `AGENTS.md` or `opencode.json` `instructions`).

Toggle command `/unslop-voice off|light|default|strict`:

- Claude Code: `adapters/toggle-command.md` → `~/.claude/commands/unslop-voice.md`.
- OpenCode: `adapters/toggle-command.md` → `~/.config/opencode/commands/unslop-voice.md`.
- Codex: no slash file; invoke the skill explicitly with `$unslop-voice <level>`.
