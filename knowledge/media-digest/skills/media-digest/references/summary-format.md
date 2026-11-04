# Summary format

Goal: a reader who never opens the transcript still gets every fact. Shorter means fewer words per
fact, not fewer facts.

## Template for `summary.md`

```
# <title>

- Source: <url or file> · <channel> · <upload_date> · <duration>
- Transcript: <manual | auto | whisper> captions, language <lang>. <Reliability note.>

## Overview
Three to five sentences: what the item is, who speaks, the main claims.

## Sections
### <topic or chapter title> [hh:mm:ss–hh:mm:ss]
- Claim, with its numbers, names, dates and conditions.
- Steps as a numbered list, in order.
- "Exact quote" [hh:mm:ss] where the wording matters.

## Entities
Name: role or meaning, first timestamp. People, products, organizations, terms, figures.

## Unclear
Passages with bad audio or suspect transcription, with timestamps.

## Omitted
Items the loss gate reported and a reason each was dropped. Empty when none.
```

## Compression

- Cut: greetings, sponsor reads, "um", repeated restatements, rhetorical questions with no content.
- Keep: every figure with its unit, every proper noun, every date, every causal claim, every
  disagreement and caveat, every instruction step, every example used to prove a point.
- Merge a repeated claim into one bullet with all its timestamps.
- Use the creator chapters in `meta.json` for sections. Without chapters, cut at topic shifts.

## Long transcripts

1. Split on chapters, or about 10 minutes (roughly 1500 words) per chunk.
2. Write each chunk's section in the template above, from that chunk only.
3. Concatenate the sections. Write the Overview and Entities last, from the sections.
4. Do not summarize the sections again. A second pass loses facts.

## Low-confidence inputs

Description-only or heavily garbled transcripts: say so under Transcript, summarize only what is
legible, and fill `Unclear`.
