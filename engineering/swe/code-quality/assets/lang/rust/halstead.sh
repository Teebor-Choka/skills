#!/usr/bin/env bash
# Halstead complexity metric — rust-code-analysis-cli, per file. Same run as
# cognitive/mi, so no new tool. Operators/operands are a per-language
# tree-sitter node-kind allowlist, a defensible approximation rather than
# Halstead's original semantics (delimiters count as operators, macros are
# special-cased), so the numbers are useful within Rust but not strictly
# comparable across languages. A file with no operands yields null difficulty
# (the tool emits null, not NaN), passed through as-is.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=rca.sh disable=SC1091
source "$script_dir/rca.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_halstead comes from sourced tools.sh
require_tools rust halstead "${rust_tools_halstead[@]}"

project_dir="$(project_dir_of "$manifest")"

rows="$(rca_root_metrics "$project_dir" | jq '[.[] | {
  file,
  volume: .metrics.halstead.volume,
  difficulty: .metrics.halstead.difficulty,
  effort: .metrics.halstead.effort,
  vocabulary: .metrics.halstead.vocabulary,
  length: .metrics.halstead.length,
  bugs: .metrics.halstead.bugs
}]')"
summary="$(jq '{analyzed: length}' <<<"$rows")"

emit_json halstead rust null null "$rows" "$summary"
