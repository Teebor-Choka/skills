# shellcheck shell=bash
# Sourced, not executed. Genuinely universal helpers, used by every metric
# script regardless of language or metric — the kind of code that belongs
# here. Metric-specific shared helpers (e.g. hotspots' git-churn logic,
# duplication's jscpd invocation) live in assets/lang/shared/ instead, one
# file per metric, not lumped in here just because more than one language
# needs them.

# Prints the subset of the given tool names that are not on PATH, as a JSON
# array (e.g. ["cargo-llvm-cov","cargo-crap"], or [] if all present) — a
# human, CI, or an agent can all parse it the same way. Safe to build by
# hand: tool names are plain identifiers, never containing characters that
# need JSON escaping.
missing_tools() {
  local tool missing=()
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("\"$tool\"")
  done
  local joined=""
  [ "${#missing[@]}" -eq 0 ] || joined="$(
    IFS=,
    echo "${missing[*]}"
  )"
  printf '[%s]' "$joined"
}

# Checks <lang>/<metric>'s required tools, printing the standard "missing
# required tools" message and exiting 3 if any are absent. Every metric
# script did this by hand (same 6 lines, only the label and tool array
# changed) before this existed.
require_tools() {
  local lang="$1" metric="$2"
  shift 2
  local missing
  missing="$(missing_tools "$@")"
  [ "$missing" = "[]" ] && return 0
  echo "code-quality:measure/lang/$lang/$metric: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/$lang.md for how to add" >&2
  echo "them." >&2
  exit 3
}

# Resolves a manifest's directory to an absolute path — several tools in
# this skill (rust-code-analysis-cli, complexipy, pyscn, git) silently
# misbehave or reject a relative path in some invocation shapes, found by
# testing each directly, so every metric script needs this same resolution.
project_dir_of() {
  (cd "$(dirname "$1")" && pwd)
}

# Builds one metric's canonical JSON envelope — the ONLY output shape every
# metric script produces, regardless of language. An agent consuming this
# skill's output should never need to parse a human-formatted table: every
# script emits this, and run.sh's --format=human derives a table FROM it
# (render_human below) rather than a script maintaining two divergent
# outputs.
#
# unit/threshold are literal JSON (pass `null`, `"score"`, `30`, etc. as
# actual arguments, not shell strings needing quoting) since not every
# metric has one; rows/summary are JSON already built by the caller (a jq
# filter's own output is valid JSON to pass straight through).
emit_json() {
  local metric="$1" language="$2" unit="$3" threshold="$4" rows="$5" summary="$6"
  jq -n \
    --arg metric "$metric" \
    --arg language "$language" \
    --argjson unit "$unit" \
    --argjson threshold "$threshold" \
    --argjson rows "$rows" \
    --argjson summary "$summary" \
    '{metric: $metric, language: $language, unit: $unit, threshold: $threshold, rows: $rows, summary: $summary}'
}

# Renders one metric's canonical JSON envelope (as built by emit_json) as a
# human-readable table. Column set and order come from the rows themselves
# (every row in one metric's output shares the same keys, in the same
# order, by construction) — this is intentionally generic rather than
# per-metric, so the human view can never drift from the JSON one; the
# tradeoff is losing each underlying tool's own formatting flourishes
# (coverage bars, colored checkmarks), which run.sh's old direct-passthrough
# design had but couldn't get from a single source of truth.
render_human() {
  local json="$1" language metric unit threshold row_count
  language="$(jq -r '.language' <<<"$json")"
  metric="$(jq -r '.metric' <<<"$json")"
  unit="$(jq -r '.unit // "n/a"' <<<"$json")"
  threshold="$(jq -r '.threshold // "n/a"' <<<"$json")"
  echo "$language:$metric (unit: $unit, threshold: $threshold)"
  row_count="$(jq '.rows | length' <<<"$json")"
  if [ "$row_count" -gt 0 ]; then
    {
      jq -r '.rows[0] | keys_unsorted | @tsv' <<<"$json"
      jq -r '.rows[] | [.[]] | @tsv' <<<"$json"
    } | column -t -s $'\t'
  else
    echo "(no rows)"
  fi
  echo -n "summary: "
  jq -r '.summary | to_entries | map("\(.key)=\(.value)") | join(", ")' <<<"$json"
}
