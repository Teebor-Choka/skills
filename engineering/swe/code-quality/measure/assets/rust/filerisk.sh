#!/usr/bin/env bash
# FileRisk metric — cargo-iceberg4rust.
#
# Standalone: pure static analysis, no coverage/build dependency, so this
# has no prerequisite chain of its own. Safe to run independently of the
# other metrics, and fanned out in parallel with them by run.sh.
set -euo pipefail

manifest="${1:-Cargo.toml}"

if ! command -v cargo-iceberg4rust >/dev/null 2>&1; then
  echo "code-quality:measure/rust/filerisk: cargo-iceberg4rust not on PATH." >&2
  echo "See ../../references/rust.md for how to add it to the nix devshell." >&2
  exit 3
fi

cargo iceberg4rust --manifest-path "$manifest" --workspace
