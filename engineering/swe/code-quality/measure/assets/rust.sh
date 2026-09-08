#!/usr/bin/env bash
# Rust runner for code-quality:measure.
#
# Deterministic — no LLM involved. Prints each tool's native report to stdout
# in run order (cheapest / fewest prerequisites first): FileRisk, then
# coverage, then CRAP. Exits nonzero and names what's missing if a required
# tool isn't on PATH; does not install anything. See ../references/rust.md
# for why these tools and thresholds were chosen.
set -euo pipefail

manifest="${1:-Cargo.toml}"

missing=()
for tool in cargo-iceberg4rust cargo-llvm-cov cargo-crap; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "code-quality:measure/rust: missing required tools: ${missing[*]}" >&2
  echo "See ../references/rust.md for how to add them to the nix devshell." >&2
  exit 3
fi

echo "== FileRisk (cargo-iceberg4rust) =="
cargo iceberg4rust --manifest-path "$manifest" --workspace

echo
echo "== Coverage (cargo-llvm-cov) =="
lcov_path="$(mktemp -t code-quality-measure)"
trap 'rm -f "$lcov_path"' EXIT
cargo llvm-cov --manifest-path "$manifest" --workspace --lcov --output-path "$lcov_path"

echo
echo "== CRAP score (cargo-crap) =="
cargo crap --manifest-path "$manifest" --workspace --lcov "$lcov_path"
