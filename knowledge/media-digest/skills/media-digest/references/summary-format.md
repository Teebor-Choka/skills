# Summary format

Goal: a reader who never opens the source still gets every fact. Shorter means fewer words per
fact, not fewer facts.

## Template for `summary.md`

```
# [<title>](<url>)

- Source: [<url>](<url>) · <channel or author> · <upload_date> · <duration or site>
- Files: [text](transcript.txt) · [metadata](meta.json)
- Text origin: <manual | auto | whisper | article>, language <lang>. <Reliability note.>

## Short summary
Two to three sentences: what this is and its main claims. Readable alone.

## Sections
### <topic, chapter or heading> [hh:mm:ss–hh:mm:ss]
- Claim, with its numbers, names, dates and conditions.
- Steps as a numbered list, in order.
- "Exact quote" [hh:mm:ss] where the wording matters.

## Entities
Name: role or meaning, first location. People, products, organizations, terms, figures.

## Unclear
Passages with bad audio, suspect transcription, or failed extraction, with locations.

## Omitted
Items the loss gate reported and a reason each was dropped. Empty when none.

## Follow-up discussion
Three to six items, each one line, none from the source itself:
- Open question the item leaves unanswered.
- Claim worth verifying, and where to check it.
- Counterpoint or limit of the argument.
- Related topic or next thing to read or watch.
- Decision or action the content suggests.
Label them as the model's own: this section is the only place for opinion.
```

## Locations

- Media: `[hh:mm:ss]` or `[hh:mm:ss–hh:mm:ss]`. `scripts/link_timestamps.py` makes them links.
- Articles: no timestamps. Name the source heading in the section title, e.g. `### Costs (section "Pricing")`.
- Never invent a location. If the text has none, omit it.

## Compression

- Cut: greetings, sponsor reads, "um", repeated restatements, rhetorical questions with no content,
  navigation, cookie banners, related-article blurbs that survived extraction.
- Keep: every figure with its unit, every proper noun, every date, every causal claim, every
  disagreement and caveat, every instruction step, every example used to prove a point.
- Merge a repeated claim into one bullet with all its locations.
- Use the creator chapters in `meta.json`, or the article headings, for sections. Without either, cut at topic shifts.

## Long text

1. Split on chapters or headings, or about 10 minutes (roughly 1500 words) per chunk.
2. Write each chunk's section in the template above, from that chunk only.
3. Concatenate the sections. Write the Short summary, Entities and Follow-up discussion last, from the sections.
4. Do not summarize the sections again. A second pass loses facts.

## Low-confidence inputs

Description-only media, garbled transcripts, or an article that extracted only in part: say so under
Text origin, summarize only what is legible, and fill `Unclear`.
