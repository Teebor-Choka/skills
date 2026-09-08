#!/usr/bin/env bash
# Duplication % metric — jscpd.
#
# Same invocation as rust/duplication.sh (run_duplication lives in
# ../_common.sh) — jscpd isn't Rust- or Python-specific, so there's nothing
# language-specific to do here beyond checking this language's own tool
# presence and pointing at this manifest's directory.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"

# shellcheck disable=SC2154 # python_tools_duplication comes from sourced tools.sh
missing="$(missing_tools "${python_tools_duplication[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/python/duplication: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/python.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

run_duplication "$(dirname "$manifest")"
