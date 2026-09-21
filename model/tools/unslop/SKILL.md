---
name: unslop
description: >
  Remove AI tells (the machine patterns that make text read as LLM-generated) and restore
  a plain, human voice, preserving meaning, facts, code, and register. Runs two ways: on
  demand to rewrite a specific target text, or always-on as a persistent house voice
  applied by DEFAULT to all natural-language output — every reply longer than a short
  two-sentence answer, and every doc, README, code comment, commit message, and PR
  description before it is written or committed. Levels off/light/default/strict, toggled
  per session with /unslop-mode. Also triggers on "unslop", "de-slop", "humanize", "make
  this sound less like AI", "remove AI-isms", or when text is called robotic, sycophantic,
  generic, or over-structured. Do not apply to a short two-sentence reply. Edits prose
  only: it is not a grammar checker, never changes code logic, and never invents facts.
---

# Unslop

Rewrite text so it stops reading as machine-generated: remove the recurring tells of
LLM prose and restore a plain, human voice, without changing meaning, facts, code, or
the author's register.

Two layers matter, in order of impact:

1. **Structure** — how the piece is shaped and argued. This is the layer detectors
   key on, and the one that survives a surface cleanup.
2. **Surface** — words, phrases, and punctuation.

Fixing only the surface barely helps: in one 61,608-text study, removing clichés moved
AI detection just 95.5% to 93.9%. Always do the structural pass too.

Lexical tells decay each model generation ("delve" collapsed through 2025; newer models
suppress em dashes on their own). Target the habit (inflation, copula avoidance,
over-explaining), not any single banned word.

## Contract (do not violate)

- **Facts first.** Never invent a specific, number, source, or threshold to make prose
  sound human. If a rewrite would change meaning, keep the meaning and find another
  phrasing. Re-verify anything you touched.
- **Prefer a no-op.** Edit only spans you are confident are tells; pass every other
  sentence through unchanged. A smaller honest edit beats a fluent rewrite.
- **Never touch** code, commands, file paths, identifiers, config, URLs, or
  quoted/cited material. Fix the prose around them.
- **Match the source register.** "More human" is not "more casual." Do not inject slang
  or filler into institutional copy, and do not replace slop with staccato anti-slop
  ("Not X. Y."). Heuristic: if the result would only fit a personal blog, you
  overcorrected.
- **Dose, not eradication.** One em dash, one triad, one hedge is fine. The failure is
  repetition and clustering. Flag the third instance, not the first.
- **Precedence when rules collide:** facts > quotations > the author's voice > domain
  register > any anti-slop rule.

## Modes and levels

Two ways to use this skill:

- **On demand** — rewrite a specific target text (when asked to "unslop this"). Run the
  full process below.
- **Always-on voice** — keep everything *you* emit de-slopped by default, every response,
  session-wide. Wire it with the output style or `AGENTS.md` baseline in `adapters/`, and
  adjust per session with `/unslop-mode off|light|default|strict` (Codex: `$unslop <level>`).

The level dials how much of the process runs; the default is **default**:

| Level | Runs |
|-------|------|
| **off** | Nothing. Raw voice. |
| **light** | Surface pass only; structure untouched. |
| **default** | Surface + structural pass. The standing everyday level. |
| **strict** | Surface + structural, applied hard and to short replies too; terse register. |

At every level except `off`, keep full content for security warnings, destructive-action
confirmations, exact errors, and quoted text — clarity wins over brevity.

## Process

1. Read once for meaning, genre, and register.
2. Scan both layers (structure, then surface). Collect all findings first; do not
   rewrite mid-scan.
3. Rewrite from the list, honoring the contract.
4. Self-audit: reread and ask "what still makes this read as AI-generated?" Fix what
   remains. Run this once; do not loop.
5. If asked to review rather than rewrite, report findings as a terse
   `location → tell → fix` list and change nothing.

## Structural pass (do this first)

Fix structure before wording. Each move is detailed in `references/patterns.md`:

- **Outline test** — the first sentence of each paragraph must not read as a clean summary.
- **Don't over-explain** — cut the sentence that states the theme or moral; let the fact carry it.
- **Name the real thing** — "Netflix", not "a streaming service"; the study, not "studies show" (real specifics only).
- **Break the template** — no hook / evidence / turn / tidy-bow shape; leave endings open.
- **Uneven confidence** — hedge the genuinely soft spots, not every sentence.

For narrative, marketing, and long-form, also apply the StoryScope signals there.

## Surface pass

Load the reference lists and apply them:

- `references/vocabulary.md` — AI words to plain replacements; abstract metaphor and
  jargon nouns to concrete; a plain-English (Google) register.
- `references/phrases.md` — openers, closers, sycophancy, disclaimers, filler,
  meta-commentary, and reasoning-chain leaks to delete.
- `references/patterns.md` — sentence-shape and rhetorical tells, punctuation and
  formatting rules, the structural/narrative catalog, and plain-speech rules.

Highest-signal surface fixes, applyable inline without the references:

- Em-dash pileups become periods or commas (keep hyphens in compounds).
- "serves as / stands as / boasts / features" become is or has.
- "Not just X, but Y" and "That's not X. That's Y." state the point once.
- Superficial "-ing" tails ("…, highlighting its importance") split into fact plus
  consequence, or get cut.
- Vague authority ("experts believe", "studies show") is named or cut.
- Chatbot openers, closers, and sycophancy ("Great question!", "I hope this helps!",
  "You're absolutely right") are deleted.
- Filler ("in order to" to "to"; "it is important to note that" cut) and hedge stacks
  ("could potentially possibly" to "may").
- Title Case headings become sentence case; decorative emoji go; curly quotes become
  straight.

Then apply the plain-speech rules from `references/patterns.md`: say the mechanism not the
feeling, one idea per sentence, active voice, cut adverbs, vary sentence length.

## Self-audit checklist

- No word or metaphor-noun from the lists survives without a reason.
- Structure passes the outline test; no theme-spelling, template wrap, or tidy bow.
- Real specifics are named, and true; no invented facts.
- Punctuation and boldface are sparing; headings sentence-case; quotes straight.
- Register matches the source; the result is not staccato or over-casual.
- Read one paragraph aloud: would a person explaining this sound like this? If not,
  keep going.

## Running across agents

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
`skill-creator` skill).

## Sources

Pooled from the main open "unslop" skills and their cited research. Full list with URLs
in `references/sources.md`. Anchors: Wikipedia "Signs of AI writing"; the cursor/pstack
unslop base; StoryScope (arXiv:2604.03136); the UMD/DeepMind cliché-removal study;
Berens & Kobak excess-vocabulary; the Google developer style word list.
