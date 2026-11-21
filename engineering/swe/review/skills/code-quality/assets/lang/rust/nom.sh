#!/usr/bin/env bash
# Number-of-methods metric — rust-code-analysis-cli, per file. Same run as
# cognitive/mi, so no new tool. Reports functions + closures per file; the
# other half of "oversized modules" (too many functions in one file),
# thresholded by a consumer rather than here.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=rca.sh disable=SC1091
source "$script_dir/rca.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_nom comes from sourced tools.sh
require_tools rust nom "${rust_tools_nom[@]}"

project_dir="$(project_dir_of "$manifest")"

rows="$(rca_root_metrics "$project_dir" | jq '[.[] | {
  file,
  functions: .metrics.nom.functions,
  closures: .metrics.nom.closures,
  total: .metrics.nom.total
}] | sort_by(-.total)')"
summary="$(jq '{analyzed: length}' <<<"$rows")"

emit_json nom rust '"count"' null "$rows" "$summary"
