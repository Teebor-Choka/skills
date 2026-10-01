---
name: prose-craft
description: >
  Make prose a pleasure to read: compose or revise clear, well-architected writing grounded
  in Strunk & White's concision and Pinker's classic style. Use whenever the user wants a
  passage of connected prose (an essay, README, doc, PR description, blog post, email, or any
  run of sentences) to read better, get tighter, or be composed well — in whatever words they
  ask. Covers the shapes: clean up the prose; make this abstract or paragraph tighter; tighten
  this design-doc paragraph that reads too wordy; make it concise and well-structured; get to
  the point; improve the flow; why does this read badly; help me write X; write the opening for
  a blog post. Also voice matching on request ("match my voice", "write in my style") when the
  user supplies a sample of their own writing. Runs a top-down pass: structure first, then
  sentence architecture, then word-level concision. Do not use to strip AI tells or humanize
  machine text (that is the unslop skill), to fix grammar or spelling, or to refactor code or
  design slides.
license: MIT
compatibility: any
metadata:
  version: "1.1.1"
---

# Prose craft

Rewrite prose so a reader moves through it without friction: clear structure, sentences the
working memory can hold, and not one word more than the meaning needs. The grounding is two
sources that agree more than they differ: Strunk and White on concision, and Pinker on
classic style, where the writer shows the reader something in the world instead of narrating
the act of explaining it.

A good run is a top-down pass, not a line-by-line scrub. You fix what a paragraph is about
before you polish a sentence inside it, because a sentence you are about to move is not worth
polishing.

## When to use

Fire on any request to draft or improve a passage of connected prose, including oblique ones:
"this reads badly", "tighten the intro", "make the README clearer", "help me phrase this".
The prose can be technical or plain; the craft is the same.

Stay quiet when the job is something else:

- **Removing AI tells** ("de-slop this", "make it sound less like a bot", "humanize it") is
  the `unslop` skill. See the boundary below.
- **Grammar and spelling** is a checker's job, not this skill's.
- **Slides, layout, or visual design** is a different domain.

## Boundary with unslop

Same goal, opposite direction. This skill **builds** a good sentence from intent. `unslop`
**subtracts** the fingerprints of machine text: a banned-word inventory, the "not just X, but
Y" shape, forced triads, emoji and sycophancy, uniform rhythm. Those lists do not belong here.

Where the two touch a shared topic, this skill states the principle once and leaves the
tell-inventory to `unslop`:

- **Concision** here is the positive rule "omit needless words". The catalog of specific LLM
  filler phrases lives in `unslop`.
- **Metadiscourse and hedging** here is Pinker's classic-style stance, a compositional
  choice. The specific hedge phrases a model overproduces live in `unslop`.
- **Nominalizations and passive voice** are taught here as craft; `unslop` only strips them
  in bulk when they read as a statistical signature.

Practical test: if an item says "prefer / build / place", it is craft and belongs here. If it
says "detect and delete this exact token or shape", it belongs to `unslop`. When a request is
really both (write it well and also scrub the tells), run this pass first, then hand off to `unslop`.

## How to run it

Two modes, plus one optional mode:

- **Compose or revise**: apply the pass to produce better prose. This is the default.
- **Review**: report findings as a terse `location → rule → fix` list and change nothing.
  Use this when the user wants to see what is wrong before you touch their text.
- **Voice matching (optional, off by default)**: bend the output toward one real writer's
  measured voice instead of the neutral ideal. Fires only when the user explicitly asks
  ("match my voice", "write in my style") and supplies a real 300+ word sample of their own.
  It layers on top of the craft pass and still defers surface tells to `unslop`. Full method
  in `references/voice-matching.md`; read it before running this mode.

The engine is a 20-item ordered checklist in `references/checklist.md`. Read that file and run
it as three sweeps, top to bottom: **structure and coherence, then sentence architecture, then
word-level concision.** The order is the point. Restructuring is cheap early and expensive
late; word-polishing comes last because it is wasted on a sentence you are about to cut or
move. `references/canon.md` holds the reasoning behind each rule for the judgment calls; read
it when a fix is not obvious or when you need to explain a change.

The universals below hold across every audience. Everything else is register, and register
tracks the audience and surface: a reference doc stays neutral, an internal note can use
contractions, a landing page can run warmer. Do not flatten a piece into one house voice.

- Active voice with a named actor doing a real action.
- The specific, concrete word over the general and abstract one.
- Cut every word that does no work.
- Lead with the answer; put the point up front, not after a wind-up.
- One idea per sentence; vary sentence length.

One meta-rule keeps the checklist from producing wooden prose: these are strong defaults, not
gates. Break any of them sooner than write something stiff or unclear. A rule that is fighting
a good sentence loses.

## The pass, in brief

Full per-item checks and provenance are in `references/checklist.md`. The shape:

- **Tier A, structure and coherence.** One point per paragraph, stated up front. Every
  sentence serves its section's claim. Given information before new. A consistent topic
  string. Explicit connectives. No metadiscourse.
- **Tier B, sentence architecture.** Concrete actor as subject, strong verb as predicate.
  Kill nominalizations. Keep subject and verb close. Heavy material to the end, no deep
  nesting. Every pronoun resolves to one nearby antecedent. Parallel form for coordinate
  ideas. Break loose and/but/so chains. Emphatic word last.
- **Tier C, word-level concision and precision.** Omit needless words. Definite and concrete
  over abstract. Positive form. Cut qualifiers and intensifiers. Plain word over jargon, and
  gloss any term of art. One tense and register.

## Self-check before you hand it back

- Read the first sentence of each paragraph in order. Do they form a coherent outline?
- Read one paragraph aloud. Would a person explaining this out loud sound like this?
- Did you change any fact, number, quote, or citation? If so, undo it. This skill changes
  wording, never meaning.
- **When composing from scratch, do not invent concrete specifics the user did not supply**:
  numbers, counts, durations, names, quotes. A vivid detail you made up is a
  fabrication, not craft. Use a placeholder the user can fill (`[N] minutes`, `[team count]`)
  or phrase it generally. Revising has the source to hold to; composing does not, which is
  exactly where invented "facts" slip in.

## Running across agents

One portable `SKILL.md` runs unchanged on Claude Code, Codex, and OpenCode. On-demand use
needs no adapter. Install the skill directory at `~/.claude/skills/prose-craft/` (Claude
Code), `~/.agents/skills/prose-craft/` (Codex), or `~/.config/opencode/skills/prose-craft/`
(OpenCode, which also reads `.claude/skills` and `.agents/skills`, so one directory serves all
three).

Two optional adapters, in `adapters/`:

- `adapters/command.md`: an explicit invoke command for Claude Code (`~/.claude/commands/`)
  and OpenCode (`~/.config/opencode/commands/`).
- `adapters/always-on.md`: a thin standing nudge for `AGENTS.md` (Codex, OpenCode) or
  `CLAUDE.md` (Claude Code): when composing longer-form prose, run the Tier A and B
  composition pass. It defers all surface cleanup and AI-tell removal to `unslop`, so the two
  do not compete. Keep it thin on purpose; it is not a second always-on voice.

## Sources

Grounded in Strunk and White's _The Elements of Style_ and Pinker's _The Sense of Style_, with
convergent guidance from the Google, Microsoft, and Economist style guides. Full citations with
URLs in `references/sources.md`.
