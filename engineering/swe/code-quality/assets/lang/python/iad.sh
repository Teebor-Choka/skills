#!/usr/bin/env bash
# I/A/D metric — Robert C. Martin's Instability/Abstractness/Distance from
# the Main Sequence (Agile Software Development: Principles, Patterns, and
# Practices, 2002), via pyscn.
#
# No Rust equivalent: no verified tool computes these formulas for Rust (see
# references/rust.md's Known limitation) — this script has no rust/ sibling.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"
project_dir="$(project_dir_of "$manifest")"

# shellcheck disable=SC2154 # python_tools_iad comes from sourced tools.sh
require_tools python iad "${python_tools_iad[@]}"

# pyscn's own progress/summary output goes to stderr; --output - routes the
# JSON report to stdout instead of a .pyscn/reports/ file.
raw="$(pyscn analyze --json --output - --skip-clones "$project_dir" 2>/dev/null)"

rows="$(jq '[.system.dependency_analysis.module_metrics // {} | to_entries[] | {
  module: .key,
  ca: .value.afferent_coupling,
  ce: .value.efferent_coupling,
  instability: .value.instability,
  abstractness: .value.abstractness,
  distance: .value.distance
}]' <<<"$raw")"
summary="$(jq '{modules: length}' <<<"$rows")"

emit_json iad python null null "$rows" "$summary"
