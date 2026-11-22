---
name: unslop
description: >
  Strip AI tells from prose and restore a plain human voice; always on for replies over two
  sentences, docs, commit and PR text. Use for "/unslop", "de-slop", "humanize", "sounds like
  AI", "robotic". Technical text follows ASD-STE100.
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
- **No em dashes.** Zero, in chat and files; recast with a comma, colon, or period.
- **Dose, not eradication.** One triad or one hedge is fine. The failure is
  repetition and clustering. Flag the third instance, not the first.
- **Concise, precise, exact, to the point.** Fewest words that keep the meaning: one idea per
  sentence, cut every qualifier and restatement that carries nothing. This is concision, not the
  staccato "Not X. Y." tell, and it never overrides the rules above — keep facts, caveats,
  quotations, and exact strings even when they cost words.
- **Precedence when rules collide:** facts > quotations > the author's voice > domain
  register > any anti-slop rule.
- **Technical text uses ASD-STE100.** For procedures, troubleshooting, error explanations,
  technical descriptions, code comments, and commit bodies, the domain register is
  Simplified Technical English (see "Technical register" below).

## Modes and levels

Read `references/modes.md` when choosing on-demand vs always-on use, the de-slop level
(`off|light|default|strict`), or the length budget (`terse|normal|full`).

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

- Em dashes become periods, commas, or colons (keep hyphens in compounds).
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

## Technical register: ASD-STE100

When the text is technical, write it in ASD-STE100 Simplified Technical English at every
level except `off`. Full rules, scope, and exceptions are in `references/ste100.md`. The
core rules:

- One word, one meaning; the same term for the same thing throughout.
- Instructions: imperative, one per sentence, 20 words maximum, condition first.
- Descriptions: present tense, active voice, 25 words maximum.
- Keep articles. No "-ing" verbs, no perfect tenses, noun clusters of three words or fewer.
- Steps as a numbered list; warnings start with the command, then the reason.

STE overrides the plain-speech rules on sentence length, slack, and voice for technical
text. It does not license the staccato tell: short sentences stay whole sentences.

## Self-audit checklist

- No word or metaphor-noun from the lists survives without a reason.
- Structure passes the outline test; no theme-spelling, template wrap, or tidy bow.
- Real specifics are named, and true; no invented facts.
- Punctuation and boldface are sparing; headings sentence-case; quotes straight.
- Register matches the source; the result is not staccato or over-casual.
- Technical text follows ASD-STE100 (`references/ste100.md` self-check).
- Read one paragraph aloud: would a person explaining this sound like this? If not,
  keep going.

## Running across agents

Read `references/agents.md` when installing the skill or wiring the always-on voice and the
`/unslop-mode` toggle on Claude Code, Codex, or OpenCode.

## Sources

Pooled from the main open "unslop" skills and their cited research. Full list with URLs
in `references/sources.md`. Anchors: Wikipedia "Signs of AI writing"; ASD-STE100 Issue 9; the cursor/pstack
unslop base; StoryScope (arXiv:2604.03136); the UMD/DeepMind cliché-removal study;
Berens & Kobak excess-vocabulary; the Google developer style word list.
