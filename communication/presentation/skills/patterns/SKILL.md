---
name: patterns
description: >
  Plan, build or review a talk, slide deck, keynote or pitch: picks techniques from 88
  presentation patterns and antipatterns. Use for "help me with my slides", "review my deck".
---

# Presentation Patterns

A pattern language for talks, built on the teachings of Neal Ford, _Presentation
Patterns_ (Ford, McCullough, Schutta, 2012). **88 items — 63 patterns (P), 25
antipatterns (AP)** — organized by the three phases of making a presentation.

Each reference file holds one terse entry per item:
`**Name** (P) — intent. How: mechanics. Avoid: caution. See: related.` (antipatterns
use `Fix:` for the remedy). **Load only the reference file(s) for the phase you're
in** — don't read all of them at once. Use this SKILL.md catalog to spot the
relevant item, then open its reference file for the full technique.

## Phases → files

| Phase       | Do                                                            | Files to load                                                                          |
| ----------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **Prepare** | Decide why/for-whom, generate & structure ideas, pick a shape | `references/01-prelude.md`, `references/02-creativity.md`                              |
| **Build**   | Design slides, control reveal over time, plan demos/code      | `references/03-slides.md`, `references/04-temporal.md`, `references/05-demos.md`       |
| **Deliver** | Ready the room, perform, avoid stage mistakes                 | `references/06-stageprep.md`, `references/08-perf.md`, `references/07-antipatterns.md` |

Pre-flight before any delivery: skim **`07-antipatterns.md`** as a "do-not" checklist.

## Review a deck (the linter)

Scoring a real `.pptx`/`.pdf` against the patterns (the `review.mjs` invocation, tiers, `--fix`): read [references/linter.md](references/linter.md).

## Catalog

Selector tags below are ≤6-word reminders; open the file for the real entry.

### Prepare

**01-prelude.md** — Prelude

- Big Why (P) — why you're giving this talk
- Know Your Audience (P) — research who's in the room
- Proposed (P) — get accepted via a polished CFP
- Required (P) — command-performance talk you must give
- Social Media Advertising (P) — promote to boost attendance
- Abstract Attorney (AP) — audience polices your abstract

**02-creativity.md** — Creativity

- Fourthought (P) — ideate→capture→organize→design, stay out of the tool
- Concurrent Creation (P) — build out of order; sane group decks
- Crucible (P) — refine under pressure of performing
- Narrative Arc (P) — structure the talk as a story
- Triad (P) — three central ideas, three acts
- Talklet (P) — compose from ~20-min self-contained pieces
- Lightning Talk (P) — fixed short/auto-advancing format
- Takahashi (P) — huge one-word slides, fast
- Expansion Joints (P) — short/medium/long variants
- Brain Breaks (P) — re-engage every 10–20 min
- Cave Painting (P) — one zoomable canvas (Prezi-style)
- Unifying Visual Theme (P) — one repeating visual tie
- Leet Grammars (P) — insider slang to bond/perceive
- Celery (AP) — more chewing than nutrition
- Alienating Artifact (AP) — risqué device disenfranchises audience

### Build

**03-slides.md** — Slide construction

- Defy Defaults (P) — never ship stock templates
- Analog Noise (P) — imperfection adds interest/believability
- Á la Carte Content (P) — reorderable slides on the fly
- Composite Animation (P) — stack simple animations for effect
- Foreshadowing (P) — seed an idea to resolve later
- Vacation Photos (P) — images replace wordy slides
- Coda (P) — appendix for un-spoken material
- Greek Chorus (P) — seeded voices/personas to interject
- Peer Review (P) — critique the draft before it's final
- Bullet-Riddled Corpse (AP) — every slide a bullet dump
- Cookie Cutter (AP) — padding to fill a slide
- Ant Fonts (AP) — tiny fonts to cram content
- Fontaholic (AP) — cacophony of fonts
- Photomaniac (AP) — clip-art clutter in empty space
- Floodmarks (AP) — branding invades content area
- Injured Outlines (AP) — a single lone sub-bullet
- Borrowed Shoes (AP) — delivering someone else's talk

**04-temporal.md** — Over time

- Context Keeper (P) — reveal the talk's structure
- Bookends (P) — distinct slides wrap the whole talk
- Breadcrumbs (P) — agenda trail showing progress
- Intermezzi (P) — section wraps within the talk
- Exuberant Title Top (P) — idea centers then migrates up
- Gradual Consistency (P) — reveal bit by bit
- Charred Trail (P) — gray out covered content
- Soft Transitions (P) — imperceptible fades between states
- Backtracking (P) — repeat to re-establish context
- Invisibility (P) — elements hidden from the printout
- Crawling Credits (P) — scrolling bottom-to-top credits
- Preroll (P) — looping title/topic before you start
- Infodeck (P) — deck meant to be read, not presented
- Slideuments (AP) — deck trying to be slides + handout

**05-demos.md** — Demos and code

- Live Demo (P) — run it live for credibility (high risk)
- Lipsync (P) — pre-record the tool interaction
- Live on Tape (P) — record the whole talk, deliver electronically
- Emergence (P) — gradually reveal a big thing
- Crawling Code (P) — show code a portion at a time
- Traveling Highlights (P) — move a highlight across the slide
- Dead Demo (AP) — live demo as time-filler

### Deliver

**06-stageprep.md** — Stage prep

- Preparation (P) — checklist against Murphy's Law
- Seeding Satisfaction (P) — warm up the audience beforehand
- Posse (P) — plant friendly faces/allies
- Display of High Value (P) — signal speaker brings new knowledge
- Shortchanged (AP) — coping with a last-minute time cut

**08-perf.md** — Performance

- Carnegie Hall (P) — the only prep is practice
- Stakeout (P) — arrive early via a nearby staging spot
- Shoeless (P) — creature comforts put you at ease
- Weatherman (P) — never turn your back; stand aside
- Lightsaber (P) — minimal, thoughtful laser-pointer use
- Breathing Room (P) — purposeful pauses to let ideas settle
- Emotional State (P) — read and adapt to the audience mood
- Entertainment (P) — season lightly; don't drown the message
- Mentor (P) — guide the audience like a tutor
- Make It Rain (P) — props to add flair and pull in the shy
- Seeding the First Question (P) — plant a question to break Q&A ice
- Echo Chamber (P) — repeat each question before answering
- Red, Yellow, Green (P) — instant card-vote feedback

**07-antipatterns.md** — Performance antipatterns (pre-flight "do-not" list)

- Hiccup Words (AP) — umm/ahh fillers
- Going Meta (AP) — talking about the talk
- Disowning Your Topic (AP) — over-hyping or condescending
- Tower of Babble (AP) — jargon above the audience
- Negative Ignorance (AP) — "who here does NOT know X?"
- Bunker (AP) — hiding behind the podium
- Laser Weapons (AP) — laser pointer as a crutch
- Hecklers (AP) — hostile audience members
- Backchannel (AP) — live text/tweet chatter
- Dual-Headed Monster (AP) — serving live + remote at once
- Lipstick on a Pig (AP) — effects over weak content

## Notes

- **Credit:** built on the teachings of Neal Ford, _Presentation Patterns_ (Ford,
  McCullough, Schutta, Addison-Wesley, 2012). The pattern names are theirs; the
  entries are short paraphrased guidance, and no book text is bundled.
- **Integrity check:** `python3 scripts/verify.py` confirms every item in the
  plugin's registry (`scripts/registry.mjs`) is present, correctly typed, and in
  its reference file.
- **Evals:** `evals/evals.json` holds the test set.
