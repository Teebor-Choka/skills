#!/usr/bin/env bash
# CRAP metric — pytest+coverage.py generates coverage, crap4py scores it.
#
# Same shape as Rust's lang/rust/crap.sh: not fully independent (CRAP needs
# a coverage report first), and accepts a pre-generated lcov file as a
# second argument to skip regenerating coverage here.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"
supplied_lcov="${2:-}"

# shellcheck disable=SC2154 # python_tools_crap comes from sourced tools.sh
require_tools python crap "${python_tools_crap[@]}"

# No pyproject.toml parsing to guess a src/ layout — the manifest's own
# directory is treated as the project root for both test discovery and
# coverage measurement. Documented as an explicit assumption in
# ../../references/python.md, not a guessed convention.
#
# pytest and crap4py must both compute their relative paths from the SAME
# cwd for the LCOV file's SF: entries to match what crap4py looks up, or
# coverage silently reads back as N/A instead of erroring — found by running
# this against a real fixture from a different starting directory than the
# manifest's own. project_dir_of's absolute resolution is what makes that
# cwd stable regardless of where this script itself was invoked from.
project_dir="$(project_dir_of "$manifest")"

if [ -n "$supplied_lcov" ]; then
  lcov_path="$(cd "$(dirname "$supplied_lcov")" && pwd)/$(basename "$supplied_lcov")"
else
  lcov_path="$(mktemp -t code-quality-measure.XXXXXX)"
  trap 'rm -f "$lcov_path"' EXIT
  # pytest's own progress output goes to stderr so stdout carries only the
  # crap4py report — run.sh captures each branch's stdout for the summary.
  # cd + "." (not an absolute --cov path) keeps pytest's relative paths
  # consistent with crap4py's below, run from the same directory.
  (cd "$project_dir" && pytest --cov=. --cov-branch --cov-report="lcov:$lcov_path") 1>&2
fi

threshold=30
raw_table="$(cd "$project_dir" && crap4py . --lcov "$lcov_path")"

# crap4py has no --json/--format flag at all (checked its own --help
# directly) — its only output is this column-aligned table, no line number
# included. Parsed on 2+ space runs, which is safe here since none of
# crap4py's own columns (function/module names, then plain numbers) ever
# contain repeated spaces themselves.
rows="$(tail -n +5 <<<"$raw_table" | awk -F'  +' -v threshold="$threshold" '
  NF >= 5 {
    cov = $4; gsub(/%/, "", cov)
    flagged = ($5 + 0 > threshold) ? "true" : "false"
    printf "{\"function\":\"%s\",\"file\":\"%s\",\"line\":null,\"cc\":%s,\"coverage\":%s,\"crap\":%s,\"flagged\":%s}\n", $1, $2, $3, cov, $5, flagged
  }
' | jq -s .)"
summary="$(jq --argjson threshold "$threshold" '{
  analyzed: length,
  flagged: ([.[] | select(.crap > $threshold)] | length)
}' <<<"$rows")"

emit_json crap python '"score"' "$threshold" "$rows" "$summary"
