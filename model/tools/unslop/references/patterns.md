# Patterns: sentence shape, punctuation, structure, voice

The surface word and phrase lists live in `vocabulary.md` and `phrases.md`. This file
covers the higher-signal layers: how sentences are shaped, how the piece is structured,
and how to write plainly. The structural section matters most, since surface cleanups
barely move detection.

## Sentence-shape and rhetorical tells

- **Negative parallelism** — "Not just X, but Y", "Not only X but also Y", "It's not X,
  it's Y", "less about X than about Y", "X doesn't just A; it B". Fix: state the point
  once; if Y beats X, show Y and don't mention X.
- **Contrastive definition** — "That's not X. That's Y.", the affirm-then-negate
  template (the common "cleaned-up" slop shape). Fix: state the positive claim alone.
  Exempt genuine corrections: imperative ("Use pnpm, not npm"), numeric ("Latency fell
  40%, not 4%"), authenticity ("real, not a forgery").
- **Rule of three / reflex triads** — "fast, simple, and reliable"; three parallel
  clauses. Fix: use the natural count (one, two, or four) and expand the one that
  matters.
- **False range / empty merism** — "from startups to enterprises", "from concept to
  launch", "spanning everything from", "ranging from X to Y" where no real scale exists.
  Fix: list what you mean, or name the one thing.
- **Synonym cycling / elegant variation** — rotating "the protagonist / the key player /
  the central figure", or "said / stated / noted / remarked", to dodge repetition. Fix:
  repeat the word, or use a pronoun.
- **Superficial -ing tails** — a participle bolted to a fact: "…, highlighting /
  underscoring / reflecting / ensuring / showcasing its status as…". Fix: split into two
  sentences (fact, then consequence and whose judgment), or delete.
- **Copula avoidance** — "serves as / stands as / acts as / functions as / represents /
  constitutes / marks / features / offers / boasts / maintains", "X refers to…" as a lead
  definition, "began his career as". Fix: is, are, has.
- **Rhetorical-question opener** — "What does this mean for…?", "Why should you care?",
  self-answered questions. Fix: state the answer.
- **Dramatic fragmentation / mic-drop** — "Noun. That's it.", "X. And Y. And Z.", clipped
  one-line punches. Fix: complete sentences; don't stack short fragments.
- **False concession** — "Despite these challenges, X continues to…", "While X is
  promising, Y remains a challenge", a "Challenges and Future Outlook" section. Fix: name
  concrete risks with owners and magnitudes, then stop.
- **Negation tails** — ", not X.", ", no X either." when the positive statement already
  carries the fact. Fix: drop the tail unless it preempts a real misreading ("per host,
  not per request" stays).
- **False agency / anthropomorphism** — "the numbers speak for themselves", "the data
  tells a story", "the suite defends itself". Fix: name the mechanism and what it shows
  or does.
- **Parenthetical hedging** — "(and perhaps more importantly, …)", "(arguably …)". Fix:
  its own sentence if it matters, else cut.
- **Both-sidesism** — "each perspective has merit", "the answer is not straightforward",
  "depends on various factors" that dodges a needed call. Fix: pick a side or name the
  concrete tradeoff.
- **Novelty inflation** — "coined the phrase", "the insight everyone's missing", "what
  nobody tells you about". Fix: describe what it does; claim novelty only if provable.
- **Numbered-list inflation** — "Three key takeaways", "Five things to know". Fix: use a
  count only when it is meaningful.
- **Organic-consequence framing** (agentic output) — "falls out naturally", "emerges
  organically", "a natural consequence". Fix: name who decided, or the derivation step.
- **Fallback diagnoses** (code) — "race condition / memory leak / deadlock" asserted with
  no mechanism. Fix: name the racing operations or the leaked allocation.

## Punctuation and formatting

- **Em dash** — the most-cited tell. Default to zero; recast with a comma, colon,
  parentheses, period, or two sentences. Keep hyphens in compound words.
- **En dash** — use a hyphen for ranges (`10-20`); don't use it as an em dash.
- **Colons** — avoid the "setup: reveal" habit ("The answer is:", "Here's the thing:")
  and mid-sentence connective colons. Colons are fine before a genuine list or example.
- **Boldface** — not on every key term, proper noun, or acronym. Reserve for what the
  reader would miss (roughly one or two per section). A bold lead label ending in a
  period, followed by new detail, is fine.
- **Inline-header lists** — "**Performance:** Performance improved…" (bold label
  restating the line). Fix: convert to prose, or make the lead-in add genuinely new
  detail. Don't bullet-ify flowing prose of fewer than four items.
- **Emoji** — none in headings or bullets unless the genre demands it.
- **Title case** — headings and body in sentence case ("Digital Transformation Journey"
  becomes lowercase).
- **Quotes** — pick straight or curly and hold it; mixed curly-and-straight in one
  document is a copy-paste artifact. Default straight for web. Never use zero-width or
  thin-space characters (a forensic tell).
- **Exclamation marks** — none except in quoted UI or code.
- **Chatbot debris** — delete `---` rules dropped before headings, code fences wrapping
  prose, tracking params (`utm_source=chatgpt.com`, `referrer=grok.com`), citation
  scaffolding (`oaicite`, `[cite: 3]`, `turn0search0`), and placeholders (`[Your Name]`,
  `2025-XX-XX`).
- **Improvised hyphen compounds** — "review-shaped output", "read-path ownership",
  "-aware/-local" coinages. Keep only an established shared term, a code identifier, or
  spell it out. Density matters: several per paragraph fail even if each passes alone.

## Structural and narrative layer (do this first, it matters most)

Surface cleanups barely move structural detectors. These are the shape-level tells.

- **The outline test** — read the first sentence of each paragraph in order. A clean
  summary means a machine-shaped document; reorder, merge, or start a section somewhere
  unexpected. Exempt specs and runbooks.
- **Over-determination** — AI states its own theme or moral far more than humans do (one
  study: 77% vs 52%). Cut the lesson sentence; let the fact carry it.
- **Vague allusion vs real specifics** — humans name real texts, brands, and places about
  twice as often. Name Netflix, not "a streaming service"; name the study, not "studies
  show". The cheapest high-signal humanizing move, but only with true specifics.
- **Template symmetry** — hook, then numbered evidence, then a turn, then a tidy
  question or bow. Also the recap loop: opening vocabulary that vanishes then returns at
  the end. Break the template mid-thought; leave the ending open.
- **Uniform confidence** — every paragraph at the same polished certainty. Leave one or
  two half-pressure sentences on the genuinely soft spots. Confidence should be uneven,
  with hedges on the actual weak points.
- **Clean slop (model house style)** — what survives a first cleanup: an aphoristic
  one-liner closing every paragraph, balanced antitheses replacing triads, hooks like
  "The real question is", verdict verbs on studies ("quietly kills"). Budget at most one
  aphoristic close per piece.
- **Agentic over-structuring** — a one-line fix wrapped in "What changed / Tests / Notes
  / Next steps"; generic benefit tails ("this keeps the change focused"); a direct answer
  buried under "depending on" branches; unsupported completion claims ("implemented and
  verified", "all checks pass"); bare reassurance ("this is safe" with no condition).
  Fix: name the concrete gain, the prevented failure, or the actual scope; or delete.

### Narrative-only signals (fiction, marketing, long-form)

Gate these by register; skip for docs and code. From StoryScope (arXiv:2604.03136), where
a classifier detects AI fiction from structure alone at ~93% macro-F1.

- **N1 Over-explains the theme / moralizes** — the strongest, most universal tell. Cut
  the lesson; let events carry it.
- **N2 Vague allusions instead of the real world** — name the real text, brand, or place.
- **N3 Over-writes body and senses** — AI renders emotion physically far more than humans,
  who often just name it. Keep one sensory beat, cut the reflex.
- **N4 Tidy, linear, single-track arcs** — protagonist-driven, no subplots, neat
  acceptance endings. Vary the opening and the arc across pieces.
- **N5 Narrow repertoire** — safe, central choices. Allow one morally ambivalent or
  unsafe choice.

## Plain-speech rules

- **Say the mechanism, not the feeling** — ".toSQL() returns the exact string sent" beats
  "the database stays close at hand". If you can't restate it as a concrete
  instruction, fact, or number, cut it. If a sentence could appear unchanged in another
  project's docs, it says nothing about this one.
- **One idea per sentence** — if the reader backtracks to parse it, split or drop clauses.
- **Active voice, name the actor** — "the compiler validates queries", not "queries are
  validated". Passive only when the actor is unknown or truly irrelevant.
- **Cut adverbs or use a stronger verb** — "runs quickly" to "is fast" or the number; an
  adverb propping a weak verb means the verb is wrong.
- **Kill mannered prose** — aphorisms, rhetorical fragments, personified code ("the plan
  holds it"), figurative verbs ("rides along"). Say what you mean.
- **No over-compression** — no dropped articles, verbless fragments, or symbol-speak
  ("→", "vs", "exit 2, no write"). Write whole sentences; spell out arrows and
  abbreviations.
- **Vary sentence length** — mix short and long deliberately; a uniform mid-length rhythm
  reads as machine-paced.
- **Leave slack** — one or two half-pressure sentences per piece, sitting on the real
  soft spots. Not fake typos or inserted "um".
- **Add voice** — state an opinion, react to a fact, use first person where it fits, be
  concrete. Allow some structural imperfection.
- **Hedge economy** — insure a fragile point once, not every sentence. Prefer calibrated
  words (unlikely / plausible / probable / almost certain) to false numeric confidence.
