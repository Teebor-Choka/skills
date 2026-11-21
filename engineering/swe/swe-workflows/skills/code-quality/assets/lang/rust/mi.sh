#!/usr/bin/env bash
# Maintainability Index metric — rust-code-analysis-cli, per file. Comes from
# the same run already required for cognitive complexity, so no new tool.
# Headline is mi_visual_studio (0–100, higher is better; commonly-cited bands
# >=20 good / 10–19 moderate / <10 poor). mi_sei uses log2 rather than the
# textbook natural log, so treat it cautiously. A file with no operands yields
# a null MI (the tool emits null, not NaN), passed through as-is.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=rca.sh disable=SC1091
source "$script_dir/rca.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_mi comes from sourced tools.sh
require_tools rust mi "${rust_tools_mi[@]}"

project_dir="$(project_dir_of "$manifest")"

rows="$(rca_root_metrics "$project_dir" | jq '[.[] | {
  file,
  mi_original: .metrics.mi.mi_original,
  mi_sei: .metrics.mi.mi_sei,
  mi_visual_studio: .metrics.mi.mi_visual_studio
}]')"
summary="$(jq '{analyzed: length}' <<<"$rows")"

emit_json mi rust '"index"' null "$rows" "$summary"
