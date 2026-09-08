#!/usr/bin/env bash
# CRAP metric — cargo-llvm-cov generates coverage, cargo-crap scores it.
#
# Not fully independent like filerisk.sh: CRAP mathematically needs a
# coverage report as input, so this script runs that pair sequentially
# inside itself. It's still fanned out as one parallel branch alongside
# filerisk.sh by run.sh — the sequencing is an inherent tool constraint,
# not something a design change here removes.
set -euo pipefail

manifest="${1:-Cargo.toml}"

missing=()
for tool in cargo-llvm-cov cargo-crap; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "code-quality:measure/rust/crap: missing required tools: ${missing[*]}" >&2
  echo "See ../../references/rust.md for how to add them to the nix devshell." >&2
  exit 3
fi

lcov_path="$(mktemp -t code-quality-measure.XXXXXX)"
trap 'rm -f "$lcov_path"' EXIT

# cargo-llvm-cov's own progress output goes to stderr so stdout carries only
# the CRAP report — run.sh captures each branch's stdout for the summary.
cargo llvm-cov --manifest-path "$manifest" --workspace --lcov --output-path "$lcov_path" 1>&2
cargo crap --manifest-path "$manifest" --workspace --lcov "$lcov_path"
