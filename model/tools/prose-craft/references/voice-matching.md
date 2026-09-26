# Voice matching (optional, off by default)

Most runs aim at a clear neutral ideal. Voice matching aims somewhere else: at _this
writer's_ voice. Use it only when the user explicitly asks for it and hands you a real
sample of their own writing. It is never part of the default compose or review pass.

The method is measurement, not impression. You read concrete features off a sample, edit
so those features survive, then re-measure to prove you did not quietly drift back toward
generic prose. The mechanics here are adapted from the MIT-licensed `better-writing` skill
(see `sources.md`); the invariant that matters most is its rule: **surface the writer's
voice, never invent it.**

## When it fires

- The user says "match my voice", "write in my style", "keep my voice", "edit but keep how
  I write", or invokes the command with `voice`.
- And a usable sample exists (see the gate). No sample, no voice matching: say so and offer
  the normal pass instead.

## The gate

- **Require a real sample of 300+ words** the user wrote without AI help. More than one is
  fine; far more than a few changes little.
- **Refuse "write like [named author]".** A famous name is not a sample; it invites
  caricature. Ask for the user's own text.
- **Audit the sample for AI tells before trusting it.** A sample thick with the tells the
  `unslop` skill catches may itself be machine-written, and matching it would learn the
  wrong voice. If it reads as slop, say so and ask for a cleaner sample.

## The profile

Read these features off the sample. Rough counts are fine; you are capturing proportions,
not doing statistics.

- **Sentence length**: the median, plus the share of sentences under ~8 words and over ~30.
  Rhythm lives here.
- **Openers**: of every sentence, what starts it: a pronoun, a noun, a conjunction (And,
  But), an adverb, a verb. Note the mix.
- **Contractions**: per 100 words. "do not" vs "don't" is a voice signal.
- **Person**: first- and second-person pronouns per 100 words.
- **Hedges**: "I think", "probably", "sort of", "maybe" per 100 words. Some voices hedge; do
  not strip theirs.
- **Punctuation inventory**: per 100 sentences: parentheses, colons, dashes, questions,
  exclamations.
- **Paragraph length**: median, in sentences.
- **Idiolect**: up to five words or phrases the writer uses three or more times that are
  _not_ on any slop list. These are theirs; keep them.
- **Negative space**: what the writer never does: no exclamation marks, no semicolons, no
  rhetorical questions, no bold. This list constrains you as much as the positive one.

Also fix, once, from the sample and hold across the whole piece: person, tense, and stance
(certain, ambivalent, sceptical).

## Applying it

- Run the normal craft pass first (structure, sentence architecture, concision). Voice
  matching layers on top; it does not excuse unclear writing.
- **Preserve the sample's hedges, first-person markers, and idiosyncratic word choices unless
  one fails a clarity test you can state in a sentence.** An unusual word that appears twice
  in the sample is the writer's, not a tell.
- **Match the sample's openers and punctuation** rather than substituting generic good form.
- When drafting from the sample, **reuse its recurring phrases and openers at the sample's
  rate, never all at once**: a phrase the writer uses once per piece appears once.
- **Do not add.** No asides invented "in the writer's manner"; that is fabrication, not
  voice. Surface what is theirs; never manufacture it.
- In informal genres, edit less. Imitation fails there; subtraction is safer than imitation.

## Verifying (the load-bearing step)

- **Recompute the profile on your output.** Any axis that moved by more than about a third is
  a voice break: either justify it from the brief, or put the original back.
- **Check the known drift direction first:** contractions, first person, and hedges falling
  while average word length rises is the documented way machine editing pulls a voice toward
  formal, generic prose. If you see that pattern, you overcorrected.
- For anything over ~600 words, re-read the first and last paragraphs together. Drift toward
  formal, hedge-free, contraction-free prose shows up at the end.

## Boundary

Voice matching still defers surface tells and "humanizing" to the `unslop` skill. It does not
carry a banned-word list. Its job is to bend the output toward one real person's measured
voice, and to prove it did.
