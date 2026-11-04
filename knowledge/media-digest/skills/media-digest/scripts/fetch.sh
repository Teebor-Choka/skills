#!/bin/sh
# Fetch metadata and a transcript for a URL or local media file.
# Usage: fetch.sh SOURCE [--out DIR] [--lang CODE] [--no-auto] [--refresh]
#                 [--cookies FILE] [--model NAME]
# Prints one JSON line on stdout: {"status","source","dir"}. Logs go to stderr.
# status: ok | cached | no_transcript | blocked | video_unavailable | invalid_input | tool_missing | error
# source: manual | auto | whisper | none
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
log() { printf 'media-digest: %s\n' "$*" >&2; }
emit() { jq -cn --arg s "$1" --arg src "$2" --arg d "${3:-}" '{status:$s,source:$src,dir:$d}'; }

# Tool resolution: PATH first, then one nix shell re-exec, else stop.
if ! command -v yt-dlp >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  if [ -z "${MEDIA_DIGEST_IN_NIX:-}" ] && command -v nix >/dev/null 2>&1; then
    log "yt-dlp or jq not on PATH; re-running inside nix shell"
    MEDIA_DIGEST_IN_NIX=1 exec nix shell nixpkgs#yt-dlp nixpkgs#ffmpeg nixpkgs#jq -c "$0" "$@"
  fi
  log "need yt-dlp, ffmpeg and jq (try: brew install yt-dlp ffmpeg jq, or pipx install yt-dlp)"
  printf '{"status":"tool_missing","source":"none","dir":""}\n'
  exit 2
fi

src="" out="" lang=en no_auto="" refresh="" cookies="" model=base.en
while [ $# -gt 0 ]; do
  case $1 in
  --out)
    out=$2
    shift 2
    ;;
  --lang)
    lang=$2
    shift 2
    ;;
  --no-auto)
    no_auto=1
    shift
    ;;
  --refresh)
    refresh=1
    shift
    ;;
  --cookies)
    cookies=$2
    shift 2
    ;;
  --model)
    model=$2
    shift 2
    ;;
  -*)
    log "unknown flag $1"
    emit invalid_input none
    exit 2
    ;;
  *)
    src=$1
    shift
    ;;
  esac
done
[ -n "$src" ] || {
  log "missing SOURCE"
  emit invalid_input none
  exit 2
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
ck=""
[ -z "$cookies" ] || ck="--cookies $cookies"

slugify() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\{1,\}/-/g; s/^-//; s/-$//' | cut -c1-60; }

if [ -f "$src" ]; then
  is_file=1
  base=$(basename "$src")
  slug=$(slugify "${base%.*}")
  jq -n --arg t "${base%.*}" --arg u "$src" '{title:$t,url:$u,id:null,channel:null,upload_date:null,duration:null,chapters:[],description:""}' >"$tmp/raw.json"
else
  is_file=""
  # shellcheck disable=SC2086
  if ! yt-dlp $ck --skip-download --dump-single-json --no-warnings --no-playlist "$src" >"$tmp/raw.json" 2>"$tmp/err"; then
    cat "$tmp/err" >&2
    if grep -qiE 'sign in|bot|403|cookies' "$tmp/err"; then
      log "blocked: retry with --cookies FILE (exported from your browser)"
      emit blocked none
    elif grep -qiE 'unavailable|private|removed|not exist|unsupported url' "$tmp/err"; then
      emit video_unavailable none
    else emit error none; fi
    exit 1
  fi
  slug=$(slugify "$(jq -r '.title' "$tmp/raw.json")")-$(jq -r '.id' "$tmp/raw.json")
fi

dir=${out:-./media-digest/$slug}
mkdir -p "$dir"

if [ -s "$dir/transcript.txt" ] && [ -s "$dir/meta.json" ] && [ -z "$refresh" ]; then
  log "cached: $dir (use --refresh to refetch)"
  emit cached "$(jq -r '.transcript_source' "$dir/meta.json")" "$dir"
  exit 0
fi

meta() { # $1 = transcript source
  jq --arg src "$1" --arg lang "$lang" \
    '{title,id,channel:(.uploader // .channel // null),upload_date,duration,chapters:(.chapters // []),
      description,url:(.webpage_url // .url),extractor:(.extractor_key // "file"),
      transcript_source:$src,transcript_lang:$lang}' "$tmp/raw.json" >"$dir/meta.json"
  sha=$(shasum -a 256 "$dir/transcript.txt" | cut -d' ' -f1)
  jq --arg h "$sha" '.transcript_sha256=$h' "$dir/meta.json" >"$tmp/m" && mv "$tmp/m" "$dir/meta.json"
}

# 1. Captions: creator-made first, auto-generated unless --no-auto.
source=none
if [ -z "$is_file" ]; then
  if jq -e --arg l "$lang" '(.subtitles // {}) | keys | any(startswith($l))' "$tmp/raw.json" >/dev/null; then
    flag=--write-subs
    source=manual
  elif [ -z "$no_auto" ] && jq -e --arg l "$lang" '(.automatic_captions // {}) | keys | any(startswith($l))' "$tmp/raw.json" >/dev/null; then
    flag=--write-auto-subs
    source=auto
  fi
  if [ "$source" != none ]; then
    # shellcheck disable=SC2086
    yt-dlp $ck --skip-download $flag --sub-langs "$lang,$lang-*" --sub-format vtt --no-warnings --no-playlist \
      -o "$dir/subs" "$src" >&2 || true
    vtt=$(find "$dir" -maxdepth 1 -name "subs*.vtt" | head -n1)
    if [ -n "$vtt" ] && python3 -I "$HERE/vtt2txt.py" "$vtt" >"$dir/transcript.txt" 2>/dev/null; then
      meta "$source"
      emit ok "$source" "$dir"
      exit 0
    fi
    log "caption download or parse failed; falling back to local transcription"
    source=none
  fi
fi

# 2. Local whisper on the audio track.
if [ -n "$is_file" ]; then
  cp "$src" "$dir/audio.src"
  audio="$dir/audio.src"
else
  # shellcheck disable=SC2086
  yt-dlp $ck -x --audio-format wav --postprocessor-args "ffmpeg:-ar 16000 -ac 1" --no-warnings --no-playlist \
    -o "$dir/audio.%(ext)s" "$src" >&2 || {
    emit error none "$dir"
    exit 1
  }
  audio="$dir/audio.wav"
fi
if "$HERE/transcribe.sh" "$audio" "$model" "$lang" >"$tmp/w.vtt" &&
  python3 -I "$HERE/vtt2txt.py" "$tmp/w.vtt" >"$dir/transcript.txt"; then
  rm -f "$dir/audio.wav" "$dir/audio.src"
  meta whisper
  emit ok whisper "$dir"
  exit 0
fi

# 3. Description only: the summary must flag low confidence.
if [ "$(jq -r '.description // "" | length' "$tmp/raw.json")" -gt 0 ]; then
  jq -r '.description' "$tmp/raw.json" >"$dir/description.txt"
fi
log "no transcript could be produced for $src"
emit no_transcript none "$dir"
exit 1
