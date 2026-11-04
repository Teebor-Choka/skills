#!/bin/sh
# Transcribe AUDIO with whisper.cpp; write WebVTT to stdout. Logs go to stderr.
# Usage: transcribe.sh AUDIO [MODEL=base.en] [LANG=en]
# Models are cached in ${XDG_CACHE_HOME:-~/.cache}/media-digest/models (base.en is ~150 MB).
set -eu
audio=$1 model=${2:-base.en} lang=${3:-en}

if ! command -v whisper-cli >/dev/null 2>&1; then
  if [ -z "${MEDIA_DIGEST_WHISPER_NIX:-}" ] && command -v nix >/dev/null 2>&1; then
    MEDIA_DIGEST_WHISPER_NIX=1 exec nix shell nixpkgs#whisper-cpp nixpkgs#ffmpeg -c "$0" "$@"
  fi
  echo "media-digest: whisper-cli not found (install whisper-cpp)" >&2
  exit 2
fi

models=${XDG_CACHE_HOME:-$HOME/.cache}/media-digest/models
mkdir -p "$models"
if [ ! -s "$models/ggml-$model.bin" ]; then
  echo "media-digest: downloading ggml-$model.bin" >&2
  whisper-cpp-download-ggml-model "$model" "$models" >&2
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# whisper-cli reads 16 kHz wav; convert anything else first.
ffmpeg -nostdin -loglevel error -i "$audio" -ar 16000 -ac 1 "$work/in.wav" >&2
whisper-cli -m "$models/ggml-$model.bin" -l "$lang" -f "$work/in.wav" -ovtt -of "$work/out" >&2
cat "$work/out.vtt"
