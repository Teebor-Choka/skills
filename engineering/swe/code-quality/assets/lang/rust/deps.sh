#!/usr/bin/env bash
# Unused-dependencies metric — cargo-machete, a static source/manifest scan
# (no build, no network). Rows are declared dependencies never referenced in
# source, per crate. This cargo-machete version has no JSON output, so its text
# report is parsed; exit 0 = none, 1 = found unused, 2 = error.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_deps comes from sourced tools.sh
require_tools rust deps "${rust_tools_deps[@]}"

project_dir="$(project_dir_of "$manifest")"

set +e
raw="$(cargo-machete --skip-target-dir "$project_dir" 2>/dev/null)"
status=$?
set -e

case "$status" in
0) rows='[]' ;;
1)
  # Text format: a "<crate> -- <manifest>:" header, then tab-indented unused
  # dependency names under it.
  rows="$(awk '
    /^[^[:space:]].* -- .*:$/ { c = $0; sub(/ -- .*/, "", c); crate = c; next }
    crate != "" && /^[[:space:]]+[^[:space:]]/ {
      d = $0; gsub(/^[[:space:]]+|[[:space:]]+$/, "", d); print crate "\t" d
    }
  ' <<<"$raw" | jq -Rn '[inputs | split("\t") | {crate: .[0], dependency: .[1]}]')"
  ;;
*)
  echo "deps: cargo-machete errored (exit $status)" >&2
  exit 1
  ;;
esac

summary="$(jq '{unused: length}' <<<"$rows")"

emit_json deps rust null null "$rows" "$summary"
