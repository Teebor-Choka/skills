#!/usr/bin/env bash
# I/A/D metric (Rust) — via cargo-anatomy. The implementation, the output
# contract, and the CODE_QUALITY_IAD_EXTERNAL_SCOPE handling all live in
# ../shared/iad.sh (shared with the Python sibling, which dispatches to pyscn
# instead); this only checks the Rust tool's presence and delegates.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=../shared/iad.sh disable=SC1091
source "$script_dir/../shared/iad.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_iad comes from sourced tools.sh
require_tools rust iad "${rust_tools_iad[@]}"

emit_iad_json rust "$manifest"
