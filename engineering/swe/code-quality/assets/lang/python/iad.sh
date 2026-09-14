#!/usr/bin/env bash
# I/A/D metric (Python) — via pyscn. The implementation and output contract
# live in ../shared/iad.sh (shared with the Rust sibling, which dispatches to
# cargo-anatomy instead); this only checks the Python tool's presence and
# delegates.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=../shared/iad.sh disable=SC1091
source "$script_dir/../shared/iad.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"

# shellcheck disable=SC2154 # python_tools_iad comes from sourced tools.sh
require_tools python iad "${python_tools_iad[@]}"

emit_iad_json python "$manifest"
