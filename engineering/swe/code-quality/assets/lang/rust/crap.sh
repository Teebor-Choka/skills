#!/usr/bin/env bash
# CRAP metric — cargo-llvm-cov generates coverage, cargo-crap scores it.
#
# Not fully independent like filerisk.sh: CRAP mathematically needs a
# coverage report as input, so this script runs that pair sequentially
# inside itself, unless a pre-generated lcov file is supplied as a second
# argument — e.g. one a cached build already produced, which skips
# regenerating coverage here. It's still fanned out as one parallel branch
# alongside filerisk.sh by run.sh — the sequencing is an inherent tool
# constraint, not something a design change here removes.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"
supplied_lcov="${2:-}"

if [ -n "$supplied_lcov" ]; then
  require_tools rust crap cargo-crap
else
  # shellcheck disable=SC2154 # rust_tools_crap comes from sourced tools.sh
  require_tools rust crap "${rust_tools_crap[@]}"
fi

# Resolved to absolute: cargo-crap's own `.file` field in --format json is
# reported relative to whatever `--path` was given verbatim — an absolute
# `--path` (e.g. when the caller passed an absolute manifest path) makes
# every reported file absolute too, inconsistent with every other metric's
# relative paths. cd-ing into project_dir first and passing `--path .`
# makes the output consistent regardless of how the manifest was passed.
project_dir="$(project_dir_of "$manifest")"

if [ -n "$supplied_lcov" ]; then
  lcov_path="$(cd "$(dirname "$supplied_lcov")" && pwd)/$(basename "$supplied_lcov")"
else
  lcov_path="$(mktemp -t code-quality-measure.XXXXXX)"
  trap 'rm -f "$lcov_path"' EXIT
  # cargo-llvm-cov's own progress output goes to stderr so stdout carries
  # only the CRAP report — run.sh captures each branch's stdout for the
  # summary.
  cargo llvm-cov --manifest-path "$manifest" --workspace --lcov --output-path "$lcov_path" 1>&2
fi

threshold=30
raw="$(cd "$project_dir" && cargo crap --path . --lcov "$lcov_path" --format json --threshold "$threshold")"

rows="$(jq --argjson threshold "$threshold" '[.entries[] | {
  function,
  file: (.file | sub("^\\./"; "")),
  line,
  cc: .cyclomatic,
  coverage,
  crap,
  flagged: (.crap > $threshold)
}]' <<<"$raw")"
summary="$(jq --argjson threshold "$threshold" '{
  analyzed: (.entries | length),
  flagged: ([.entries[] | select(.crap > $threshold)] | length)
}' <<<"$raw")"

emit_json crap rust '"score"' "$threshold" "$rows" "$summary"
