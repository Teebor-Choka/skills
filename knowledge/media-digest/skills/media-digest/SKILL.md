---
name: media-digest
description: Turn a video, audio file, podcast, or web article into saved text plus a dense, loss-checked summary with a short version and follow-up discussion points. Use when given a URL (YouTube, Vimeo, conference talks, news or blog articles, anything yt-dlp or a page extractor can read) or a local media file and asked to summarize it, transcribe it, extract notes, save an article, or "tell me everything in this". For media it gets creator captions, then auto captions, then local whisper transcription; for web pages it extracts the main article text. Saves text, metadata and summary to disk. Not for live streams without a recording, DRM-protected media, paywall or access-control bypass, or PDFs.
license: MIT
compatibility: Needs a POSIX shell, python3, and either yt-dlp, ffmpeg and jq on PATH or Nix (the scripts fetch them, and trafilatura for articles, with `nix shell nixpkgs#...`). Network access for fetching.
---

# Media digest

Produce three files per item: `meta.json`, the source text (`transcript.txt` for media,
`article.txt` for a web page), and `summary.md`. The summary compresses the text by removing
filler and repetition, never by removing facts. Every summary opens with a short version and
ends with follow-up discussion points.

Use this only for content the user may legitimately access, for their own notes. Respect the
site's terms. Never write cookies or credentials into the output directory.

## Steps

1. **Fetch.** Run `scripts/fetch.sh SOURCE [--out DIR] [--lang CODE] [--no-auto] [--refresh] [--cookies FILE] [--model NAME] [--article]`.
   Default `DIR` is `$MEDIA_DIGEST_OUT/<slug>/` if that variable is set, else `./media-digest/<slug>/`.
   If the user names an output location, pass it as `--out`.
   A URL that yt-dlp cannot read is fetched as an article. `--article` skips the yt-dlp attempt.
   The last stdout line is JSON: `{"status","source","dir"}`. Act on `status`:
   - `ok` or `cached`: continue. `source` is `manual`, `auto`, `whisper` or `article`.
   - `blocked`: ask the user for a cookies file (`--cookies`), then retry.
   - `video_unavailable`, `invalid_input`: report and stop.
   - `no_transcript`: no usable text. For media only `description.txt` may exist. Say so, and mark any summary low-confidence.
   - `tool_missing`: report the install hint printed on stderr.
   - `playlist` (exit 3): nothing was fetched. `entries` lists `index`, `id`, `title`, `duration`, `url`. Fetch each
     entry with its own call and `--out <base>/<id>`, then treat every item as below. Never call `yt-dlp` directly:
     it may not be on `PATH`, and `fetch.sh` falls back to Nix.
2. **Read `meta.json` and the source text.** Check `kind` (`media` or `article`) and `transcript_source`.
   Auto captions and whisper misspell names and numbers: flag uncertain terms, never correct them silently.
3. **Write `summary.md`** in the same directory, following `references/summary-format.md`. Split long
   text into chunks, summarize each, then merge without compressing the chunk outputs again.
   With several items, give each one to its own subagent (Light or Execution tier) with the item
   directory and `references/summary-format.md`. It runs steps 2 to 5 and returns the directory and
   the gate result. Cross-item work (index, claim checks) stays in the main session.
4. **Link it.** For media, run `python3 -I scripts/link_timestamps.py DIR/summary.md DIR/meta.json`.
   It turns `[hh:mm:ss]` into deep links on YouTube and Vimeo and leaves other sources unchanged.
5. **Run the loss gate.** `python3 -I scripts/check_coverage.py DIR/<source text> DIR/summary.md`.
   It lists numbers, names and quotes present in the source but absent from the summary.
   Add each one to the summary, or list it under `## Omitted` with a reason. Repeat until it exits 0.
6. **Verify (only when the user asks to check claims).** Pick the five most checkable claims, search
   primary sources (apply the `grounded-research` skill), and write `followup-checks.md` beside the
   items: claim, status (confirmed, partly, contested, not checked), finding, source link. Mark any
   claim not searched as `not checked`.
7. **Report** the directory, the source type, the short summary, the follow-up points, anything
   uncertain, and the gate result.

## Rules

- The summary states only what the source says. Keep the model's own opinions in the follow-up section, labeled.
- Keep every number, name, date, quote, step, caveat, decision and example. Drop only filler,
  repetition and rhetorical padding.
- Reference the source properly: a markdown link to the original, relative links to the saved
  files, and a location for each claim (timestamp for media, heading for articles).
- Language other than English: pass `--lang`. Write the summary in the source language unless asked.
- Tool details, fallbacks and prior art: `references/tooling.md`.
