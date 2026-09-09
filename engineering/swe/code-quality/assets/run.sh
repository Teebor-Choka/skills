#!/usr/bin/env bash
# Generic orchestrator for code-quality:measure. Requires a modern bash
# (arrays, associative arrays, local) — a #!/usr/bin/env bash shebang picks
# up whatever's first on PATH, and a system bash predating this repo's own
# bash could in principle be older; if this ever breaks with "bad
# substitution" or similar, check `bash --version` first.
#
# Takes one or more manifest paths — one per language present in the
# project. Doesn't scan for them or opinionate about layout; the caller
# already knows which manifests exist (SKILL.md's own language-detection
# step, or a human/CI that knows their own project).
#
# stdout carries ONLY the final combined JSON — every metric script's own
# canonical output (see assets/lang/_common.sh's emit_json), collected
# under one object. Nothing else goes to stdout: an agent (the primary
# consumer — see SKILL.md) can pipe this straight into a JSON parser
# without stripping banners or table borders first. All narration
# (discovery progress, per-job markers, each tool's own stderr chatter)
# goes to stderr instead — visible to a human watching the terminal,
# irrelevant to something parsing stdout. The `report` workflow (assets/
# report.sh) is what turns this JSON into a human-readable table; this
# script doesn't format anything itself.
#
# Three phases, all deterministic — no LLM involved, and none of this is
# language-specific:
#   1. Discovery — for every (language, metric) pair across every detected
#      language, checks required tools on PATH. Metrics are labeled
#      "language:metric" (e.g. "python:crap") since two languages can
#      share a metric name.
#   2. Fan-out — every available job across ALL detected languages runs in
#      one parallel batch, not one batch per language.
#   3. Collect — every branch's JSON, combined into one object.
#
# Only the literal tool invocations in assets/lang/<language>/*.sh are
# language-specific. Adding a language means: a new assets/lang/<language>/
# directory, one more arm in each case statement below, and a matching
# references/<language>.md — this file's shape doesn't change.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lang/_common.sh disable=SC1091
source "$script_dir/lang/_common.sh"

if [ "$#" -eq 0 ]; then
  echo "usage: run.sh <manifest-path> [<manifest-path> ...]" >&2
  exit 2
fi

# --- language detection: one case arm per supported language, no guessing ---
lang_for_manifest() {
  case "$(basename "$1")" in
  Cargo.toml) echo "rust" ;;
  pyproject.toml | setup.py) echo "python" ;;
  *) return 1 ;;
  esac
}

# The static metric list for a language — not derived from anything on
# disk, so adding a metric to a language means adding it here too.
metrics_for() {
  case "$1" in
  rust) echo "filerisk crap cognitive hotspots duplication" ;;
  python) echo "crap cognitive hotspots duplication iad" ;;
  *) return 1 ;;
  esac
}

# The required-tools array for one (language, metric) pair, printed one
# tool per line. Reads the literal language-prefixed array name directly —
# no indirect expansion, no risk from this environment's shell quirks: this
# function already knows, from its own case arm, exactly which array to
# name.
# shellcheck disable=SC2154 # arrays come from lang/<lang>/tools.sh, sourced dynamically above
tools_for_job() {
  case "$1:$2" in
  rust:filerisk) printf '%s\n' "${rust_tools_filerisk[@]}" ;;
  rust:crap) printf '%s\n' "${rust_tools_crap[@]}" ;;
  rust:cognitive) printf '%s\n' "${rust_tools_cognitive[@]}" ;;
  rust:hotspots) printf '%s\n' "${rust_tools_hotspots[@]}" ;;
  rust:duplication) printf '%s\n' "${rust_tools_duplication[@]}" ;;
  python:crap) printf '%s\n' "${python_tools_crap[@]}" ;;
  python:cognitive) printf '%s\n' "${python_tools_cognitive[@]}" ;;
  python:hotspots) printf '%s\n' "${python_tools_hotspots[@]}" ;;
  python:duplication) printf '%s\n' "${python_tools_duplication[@]}" ;;
  python:iad) printf '%s\n' "${python_tools_iad[@]}" ;;
  *) return 1 ;;
  esac
}

# --- resolve each manifest to a language, reject unknowns/duplicates early ---
langs=()
declare -A manifest_of=()
for manifest in "$@"; do
  lang="$(lang_for_manifest "$manifest")" || {
    echo "code-quality:measure: no runner for this manifest yet ($manifest)." >&2
    echo "See the code-quality:measure skill's SKILL.md — do not guess a tool chain for an unsupported language." >&2
    exit 2
  }
  if [ -n "${manifest_of[$lang]:-}" ]; then
    echo "code-quality:measure: two manifests both resolved to '$lang' ($manifest and ${manifest_of[$lang]}) — pass one manifest per language." >&2
    exit 2
  fi
  manifest_of[$lang]="$manifest"
  langs+=("$lang")
  # shellcheck disable=SC1090
  source "$script_dir/lang/$lang/tools.sh"
done

# --- Phase 1: discovery, across every detected language together ---
# One array of "lang:metric" job labels, not two index-parallel arrays kept
# in sync by convention — a job's lang/metric are recovered from its own
# label (parameter expansion, no subshell) wherever needed below.
echo "== code-quality:measure discovery ==" >&2
available_jobs=()
missing_entries=()
for lang in "${langs[@]}"; do
  for metric in $(metrics_for "$lang"); do
    label="$lang:$metric"
    mapfile -t job_tools < <(tools_for_job "$lang" "$metric")
    missing="$(missing_tools "${job_tools[@]}")"
    if [ "$missing" = "[]" ]; then
      echo "  [available] $label" >&2
      available_jobs+=("$label")
    else
      echo "  [missing]   $label (needs: $missing) -- see the skill's references/$lang.md" >&2
      missing_entries+=("$(jq -n --arg label "$label" --argjson needs "$missing" '{label: $label, needs: $needs}')")
    fi
  done
done
echo >&2

if [ "${#available_jobs[@]}" -eq 0 ]; then
  echo "code-quality:measure: no metric tools available, nothing to run." >&2
  exit 3
fi

# --- Phase 2: fan-out, one batch across all languages ---
tmp_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
trap 'rm -rf "$tmp_dir"' EXIT

pids=()
for label in "${available_jobs[@]}"; do
  lang="${label%%:*}"
  metric="${label#*:}"
  manifest="${manifest_of[$lang]}"
  safe_label="${label/:/_}"
  "$script_dir/lang/$lang/$metric.sh" "$manifest" \
    >"$tmp_dir/$safe_label.out" 2>"$tmp_dir/$safe_label.err" &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=1
done

# --- Phase 3: collect ---
echo "== code-quality:measure collect ==" >&2
results="{}"
for label in "${available_jobs[@]}"; do
  safe_label="${label/:/_}"
  echo "--- $label ---" >&2
  if [ -s "$tmp_dir/$safe_label.err" ]; then
    cat "$tmp_dir/$safe_label.err" >&2
  fi
  job_json="$(cat "$tmp_dir/$safe_label.out")"
  results="$(jq --arg k "$label" --argjson v "$job_json" '. + {($k): $v}' <<<"$results")"
done

available_json="$(printf '%s\n' "${available_jobs[@]}" | jq -R . | jq -s .)"
missing_json="[]"
[ "${#missing_entries[@]}" -eq 0 ] || missing_json="$(printf '%s\n' "${missing_entries[@]}" | jq -s .)"

jq -n \
  --argjson available "$available_json" \
  --argjson missing "$missing_json" \
  --argjson results "$results" \
  '{discovery: {available: $available, missing: $missing}, results: $results}'

exit "$status"
