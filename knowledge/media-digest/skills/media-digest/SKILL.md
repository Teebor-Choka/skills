---
name: media-digest
description: Turn a video or audio source into a saved transcript plus a dense, loss-checked summary. Use when given a URL (YouTube, Vimeo, podcasts, conference talks, any site yt-dlp supports) or a local media file and asked to summarize it, transcribe it, extract notes, or "tell me everything in this video". Gets creator captions first, then auto captions, then local whisper transcription, and saves transcript, metadata and summary to disk. Not for live streams without a recording, DRM-protected media, bypassing access controls, or summarizing text pages and PDFs.
license: MIT
compatibility: Needs a POSIX shell, python3, and either yt-dlp, ffmpeg and jq on PATH or Nix (the scripts fetch them with `nix shell nixpkgs#...`). Network access for fetching.
---

# Media digest

Produce three files per item: `meta.json`, `transcript.txt`, `summary.md`. The summary compresses
the transcript by removing filler and repetition, never by removing facts.

Use this only for media the user may legitimately access, for their own notes. Respect the site's
terms. Never write cookies or credentials into the output directory.

## Steps

1. **Fetch.** Run `scripts/fetch.sh SOURCE [--out DIR] [--lang CODE] [--no-auto] [--refresh] [--cookies FILE] [--model NAME]`.
   Default `DIR` is `./media-digest/<slug>/`. If the user names an output location, pass it as `--out`.
   The last stdout line is JSON: `{"status","source","dir"}`. Act on `status`:
   - `ok` or `cached`: continue. `source` is `manual`, `auto` or `whisper`.
   - `blocked`: ask the user for a cookies file (`--cookies`), then retry.
   - `video_unavailable`, `invalid_input`: report and stop.
   - `no_transcript`: only `description.txt` may exist. Say so, and mark any summary low-confidence.
   - `tool_missing`: report the install hint printed on stderr.
2. **Read `meta.json` and `transcript.txt`.** Note `transcript_source`: auto captions and whisper
   misspell names and numbers. Flag uncertain terms instead of correcting them silently.
3. **Write `summary.md`** in the same directory, following `references/summary-format.md`. Split long
   transcripts into chunks, summarize each, then merge without compressing the chunk outputs again.
4. **Run the loss gate.** `python3 -I scripts/check_coverage.py DIR/transcript.txt DIR/summary.md`.
   It lists numbers, names and quotes present in the transcript but absent from the summary.
   Add each one to the summary, or list it under `## Omitted` with a reason. Repeat until it exits 0.
5. **Report** the directory, the transcript source, anything uncertain, and the gate result.

## Rules

- The summary states only what the transcript says. Keep opinions of the model out, or label them.
- Keep every number, name, date, quote, step, caveat, decision and example. Drop only filler,
  repetition and rhetorical padding.
- Keep timestamps so a reader can jump to the source.
- Language other than English: pass `--lang`. Write the summary in the transcript language unless asked.
- Tool details, fallbacks and prior art: `references/tooling.md`.
