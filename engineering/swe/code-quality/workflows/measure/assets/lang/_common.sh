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
