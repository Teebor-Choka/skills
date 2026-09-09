#!/usr/bin/env bash
# Cognitive Complexity metric — rust-code-analysis-cli.
#
# Pure static AST analysis, no build/coverage dependency — standalone,
# fanned out in parallel with the other metrics.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_cognitive comes from sourced tools.sh
require_tools rust cognitive "${rust_tools_cognitive[@]}"

# rust-code-analysis-cli silently analyzes nothing when -p is given a
# relative path (e.g. ".") alongside -o — an absolute path is required, found
# by testing this directly rather than trusting the --help text alone.
project_dir="$(project_dir_of "$manifest")"

tmp_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
trap 'rm -rf "$tmp_dir"' EXIT
rust-code-analysis-cli -m -p "$project_dir" -O json -o "$tmp_dir" -w 1>&2

# Recursively pulls every function-level node out of each file's nested
# `spaces` tree — the tool doesn't offer a flat function list directly.
# `file as $file` binds the value once; without it, jq re-evaluates the
# filter against each recursion's own `.` and every row silently gets its
# own function name as the "file" instead of the real path.
find "$tmp_dir" -name '*.json' -exec cat {} + | jq -s -r --arg prefix "$project_dir/" '
  def extract(file):
    file as $file
    | ( if .kind == "function" then [{file: $file, function: .name, cognitive: .metrics.cognitive.sum}] else [] end )
      + ( (.spaces // []) | map(extract($file)) | add // [] );
  [.[] as $f | ($f | extract($f.name))] | flatten
  | sort_by(-.cognitive)
  | (["Cognitive", "Function", "File"], (.[] | [(.cognitive | tostring), .function, (.file | ltrimstr($prefix))]))
  | @tsv
'
