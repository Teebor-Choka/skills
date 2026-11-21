#!/usr/bin/env bash
# Orphaned-modules metric — cargo-modules. Finds source files present on disk
# but never linked into the module tree (no `mod foo;`), which rustc's dead_code
# lint can't see (an unlinked file isn't compiled at all). Rows are
# {module, file}. cargo-modules emits human text (no JSON), parsed with color
# disabled.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_orphans comes from sourced tools.sh
require_tools rust orphans "${rust_tools_orphans[@]}"

project_dir="$(project_dir_of "$manifest")"

# cargo-modules exits nonzero when it finds orphans (a finding, not an error),
# so tolerate a nonzero exit and parse stdout regardless. NO_COLOR keeps the
# output free of ANSI escapes (there is no --no-color flag).
raw="$(cd "$project_dir" && NO_COLOR=1 cargo modules orphans 2>/dev/null)" || true

# Lines look like:  warning: orphaned module `NAME` at path/to/file.rs
lines="$(grep -E 'orphaned module' <<<"$raw" || true)"
# shellcheck disable=SC2016 # the backticks are literal in cargo-modules' output, matched as-is
rows="$(sed -E 's/.*orphaned module `([^`]+)` at ([^ ]+).*/\1\t\2/' <<<"$lines" |
  jq -Rn '[inputs | select(length > 0) | split("\t") | {module: .[0], file: .[1]}]')"
summary="$(jq '{orphans: length}' <<<"$rows")"

emit_json orphans rust null null "$rows" "$summary"
