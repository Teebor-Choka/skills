# Profile schema

`profile.md` is Markdown, so the voice-style handoff and any harness can read it as instructions.
`profile.py validate` enforces this schema. Write every section from TRAIN messages only.

```markdown
# Voice profile: <persona>

split: <split_id from split/manifest.json>
round: <0 for the first build, then the dev round it answers>

## Measured stats

(written by `profile.py skeleton`; edit only to correct)

## Habits

## Temperament

## Short messages

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
- **Habits**: how they open and close, typical length, punctuation and casing, emoji, line breaks,
  lists, greetings and sign-offs. State rates ("ends without a period in most chat messages").
- **Temperament**: directness, hedging, humor, warmth, and how they react to bad news,
  disagreement, praise and requests. One line each, with the observable marker.
- **Short messages**: the rules for replies of 25 words or fewer. What a yes, a no, a thanks, an
  acknowledgement and a question look like. Most persona failures happen here.
- **Channels and audiences**: a matrix of channel by audience with the register shift (length,
  formality, emoji, greeting). Name every channel with 3 or more train messages.
- **Lexicon**: signature words and phrases with their rough rate, and words they use where others
  would use a common alternative.
- **Never**: what they do not do. Words, punctuation, structures, tones. This list constrains as
  much as the positive ones.
- **Decisions and responses**: how they decide, commit, defer, say no, delegate, escalate; how fast
  and how firmly they answer.
- **Worked examples**: at least 3, at least one short, each `- [train:<id>] <text>` with the
  text exactly as in `split/train.jsonl`. Prefer examples that show a habit or a reaction named
  above.

## Rules the validator checks

- All nine sections present, non-empty, no `TODO` left.
- Worked examples are in TRAIN, verbatim.
- No dev or test text: no 6-token span of a held-out message (or a whole 3 to 5 token one) that
  occurs in no train message.
- 16 KB at most, so the profile fits in a generation prompt with room for the task.
