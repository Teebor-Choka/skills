# Profile schema

`profile.md` is Markdown, so the voice-style handoff and any harness can read it as instructions.
`profile.py validate` enforces this schema. Write every section from TRAIN messages only.

```markdown
# Voice profile: <persona>

split: <split_id from split/manifest.json>
round: <0 for the first build, then the dev round it answers>

## Measured stats

(written by `profile.py skeleton`; edit only to correct)

## Mental model

### Beliefs and values

### Framing

### Reasoning moves

### Emotional range

### Stance

### Compressed

### Expanded

## Habits

## Temperament

## Short messages

## Long messages

## Channels and audiences

## Lexicon

## Never

## Decisions and responses

## Worked examples

- [train:<id>] <the train message, verbatim>
```

## What each section holds

- **Measured stats**: length distribution per band and channel, casing (share of messages
  starting lowercase, all-caps words), punctuation per message (`!`, `?`, `...`, dashes, final
  period), emoji rate, top openers and closers, repeated phrases. Numbers, not adjectives.
- **Mental model**: the generative core: how the person thinks, written from TRAIN and
  `analysis.md`. Beliefs and values they argue for; how they frame a problem; their reasoning
  moves and argument shapes; emotional range and reactions; stance toward the audience and
  status; how the same mind shows up compressed (what survives in 25 words or fewer, what is
  dropped) and expanded (structure, repetition, setups, closings). Paraphrase traits; never
  quote. Every subsection is required and non-empty.
- **Habits**: how they open and close, typical length, punctuation and casing, emoji, line breaks,
  lists, greetings and sign-offs. State rates ("ends without a period in most chat messages").
- **Temperament**: directness, hedging, humor, warmth, and how they react to bad news,
  disagreement, praise and requests. One line each, with the observable marker.
- **Short messages**: the rules for replies of 25 words or fewer. What a yes, a no, a thanks, an
  acknowledgement and a question look like. Most persona failures happen here.
- **Long messages**: the rules for long form derived from the model: opening, setup, structure,
  examples, repetition, close, typical length.
- **Channels and audiences**: a matrix of channel by audience with the register shift (length,
  formality, emoji, greeting). Name every channel with 3 or more train messages.
- **Lexicon**: signature words and phrases with their rough rate, and words they use where others
  would use a common alternative.
- **Never**: what they do not do. Words, punctuation, structures, tones. This list constrains as
  much as the positive ones.
- **Decisions and responses**: how they decide, commit, defer, say no, delegate, escalate; how fast
  and how firmly they answer.
- **Worked examples**: 3 to 6, at least one short, each `- [train:<id>] <text>` with the
  text exactly as in `split/train.jsonl`. Prefer examples that show a habit or a reaction named
  above.

## Rules the validator checks

- All eleven sections and the seven mental model subsections present, non-empty, no `TODO` left.
- 3 to 6 worked examples: the model carries the voice, not a pile of samples.
- Worked examples are in TRAIN, verbatim.
- No dev or test text: no 6-token span of a held-out message (or a whole 3 to 5 token one) that
  occurs in no train message.
- 16 KB at most, so the profile fits in a generation prompt with room for the task.
