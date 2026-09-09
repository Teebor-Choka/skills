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

if [ -n "$supplied_lcov" ]; then
  lcov_path="$supplied_lcov"
else
  lcov_path="$(mktemp -t code-quality-measure.XXXXXX)"
  trap 'rm -f "$lcov_path"' EXIT
  # cargo-llvm-cov's own progress output goes to stderr so stdout carries
  # only the CRAP report — run.sh captures each branch's stdout for the
  # summary.
  cargo llvm-cov --manifest-path "$manifest" --workspace --lcov --output-path "$lcov_path" 1>&2
fi

cargo crap --path "$(dirname "$manifest")" --lcov "$lcov_path"
