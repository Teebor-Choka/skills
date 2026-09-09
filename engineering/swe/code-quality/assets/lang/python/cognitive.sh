#!/usr/bin/env bash
# Cognitive Complexity metric — complexipy.
#
# Pure static analysis, no coverage/build dependency — standalone, fanned
# out in parallel with the other metrics.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"

# shellcheck disable=SC2154 # python_tools_cognitive comes from sourced tools.sh
require_tools python cognitive "${python_tools_cognitive[@]}"

# cd into the project dir first (rather than passing it as complexipy's own
# argument) so its "path" field comes out relative to the project root —
# passing the dirname as an argument instead reports paths still prefixed
# with that argument string, inconsistent with every other metric's file
# paths here.
project_dir="$(project_dir_of "$manifest")"
tmp_json="$(mktemp -t code-quality-measure.XXXXXX)"
trap 'rm -f "$tmp_json"' EXIT
(cd "$project_dir" && complexipy . --output-format json --output "$tmp_json" -q) >/dev/null 2>&1

rows="$(jq '[.[] | {function: .function_name, file: .path, complexity}] | sort_by(-.complexity)' "$tmp_json")"
summary="$(jq '{analyzed: length}' <<<"$rows")"

emit_json cognitive python '"score"' null "$rows" "$summary"
