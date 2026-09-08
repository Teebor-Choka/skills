#!/usr/bin/env bash
# FileRisk metric — cargo-iceberg4rust.
#
# Standalone: pure static analysis, no coverage/build dependency, so this
# has no prerequisite chain of its own. Safe to run independently of the
# other metrics, and fanned out in parallel with them by run.sh.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # tools_filerisk comes from sourced tools.sh
missing="$(missing_tools "${tools_filerisk[@]}")"
if [ -n "$missing" ]; then
  echo "code-quality:measure/rust/filerisk: missing required tools: $missing" >&2
  echo "See ../../references/rust.md for how to add them to the nix devshell." >&2
  exit 3
fi

cargo iceberg4rust --manifest-path "$manifest" --workspace
