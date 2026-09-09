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
require_tools python cognitive "${python_tools_cognitive[@]}"

complexipy "$(dirname "$manifest")"
