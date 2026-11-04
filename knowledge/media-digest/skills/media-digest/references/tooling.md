# Tooling

## Resolution order

1. `yt-dlp`, `ffmpeg`, `jq` on `PATH`.
2. Else, with Nix: `scripts/fetch.sh` re-runs itself under
   `nix shell nixpkgs#yt-dlp nixpkgs#ffmpeg nixpkgs#jq -c`. Nothing is installed globally.
3. Else it stops with status `tool_missing`. Suggest `brew install yt-dlp ffmpeg jq` or `pipx install yt-dlp`.

`scripts/transcribe.sh` does the same with `nix shell nixpkgs#whisper-cpp nixpkgs#ffmpeg`.
The article path uses `trafilatura` (`nix shell nixpkgs#python3Packages.trafilatura`, or `pipx install trafilatura`).
`scripts/shell.nix` lists the same tools for an interactive `nix-shell`.

## Transcript sources

| Order | Source                         | Flag                                                        |
| ----- | ------------------------------ | ----------------------------------------------------------- |
| 1     | Creator-made captions          | default                                                     |
| 2     | Auto-generated captions        | skipped with `--no-auto`                                    |
| 3     | Local whisper.cpp on the audio | `--model base.en` (default); `small`, `medium` for accuracy |
| 4     | Video description only         | status `no_transcript`, low confidence                      |

Whisper models cache in `${XDG_CACHE_HOME:-~/.cache}/media-digest/models`. `base.en` is about
150 MB and downloads once. For non-English media use a multilingual model (`base`, `small`) and `--lang`.

## Articles

A URL that yt-dlp reports as unsupported, or cannot download, is fetched as a web page: trafilatura
extracts the main text as markdown into `article.txt`, with title, author, site and date in `meta.json`
(`kind: article`). `--article` skips the yt-dlp attempt. Pages that need JavaScript or a login
extract little or nothing: the script then returns `no_transcript`. Paywalls are not bypassed.

## Blocked or age-gated media

yt-dlp reports 403 or "sign in". Export cookies from the user's browser to a file and pass
`--cookies FILE`. Never copy that file into the output directory.

## Caching

A directory with `transcript.txt` (or `article.txt`) and `meta.json` counts as done. `--refresh` refetches.
`meta.json` stores `transcript_sha256`, so a summary can be tied to the transcript it covered.

## Prior art

Ideas from these projects (no code copied): khou/watch-video (caption, then local whisper, then
fallback tiers), ewro/didntwatch (fetch script separate from summarizing, status codes, cache),
summarize.sh (creator captions before auto captions, description fallback), trafilatura (article extraction).
