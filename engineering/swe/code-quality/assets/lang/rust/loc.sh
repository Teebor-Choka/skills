#!/usr/bin/env bash
# Lines-of-code metric — rust-code-analysis-cli, per file. Same run as
# cognitive/mi, so no new tool. Reports the LOC family per file: SLOC (source
# lines), PLOC (physical/instruction lines), LLOC (logical/statement lines),
# CLOC (comment lines), BLANK. This also answers "oversized modules" — a
# consumer thresholds SLOC/PLOC per file rather than this metric hardcoding an
# arbitrary line limit.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=rca.sh disable=SC1091
source "$script_dir/rca.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_loc comes from sourced tools.sh
require_tools rust loc "${rust_tools_loc[@]}"

project_dir="$(project_dir_of "$manifest")"

rows="$(rca_root_metrics "$project_dir" | jq '[.[] | {
  file,
  sloc: .metrics.loc.sloc,
  ploc: .metrics.loc.ploc,
  lloc: .metrics.loc.lloc,
  cloc: .metrics.loc.cloc,
  blank: .metrics.loc.blank
}] | sort_by(-.sloc)')"
summary="$(jq '{analyzed: length}' <<<"$rows")"

emit_json loc rust '"lines"' null "$rows" "$summary"
