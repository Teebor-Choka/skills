#!/usr/bin/env bash
# Duplication % metric — jscpd.
#
# Same invocation as python/duplication.sh (run_duplication lives in
# ../_common.sh) — jscpd isn't Rust- or Python-specific, so there's nothing
# language-specific to do here beyond checking this language's own tool
# presence and pointing at this manifest's directory.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_duplication comes from sourced tools.sh
missing="$(missing_tools "${rust_tools_duplication[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/rust/duplication: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/rust.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

run_duplication "$(dirname "$manifest")"
