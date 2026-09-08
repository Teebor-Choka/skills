#!/usr/bin/env bash
# Cognitive Complexity metric — complexipy.
#
# Pure static analysis, no coverage/build dependency — standalone, fanned
# out in parallel with the other metrics.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"

# shellcheck disable=SC2154 # python_tools_cognitive comes from sourced tools.sh
missing="$(missing_tools "${python_tools_cognitive[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/python/cognitive: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/python.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

complexipy "$(dirname "$manifest")"
