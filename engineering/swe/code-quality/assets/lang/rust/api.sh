#!/usr/bin/env bash
# Public API surface metric — cargo-public-api over rustdoc JSON. rustdoc JSON
# is an unstable format that normally needs a nightly toolchain; we unlock it on
# the stable toolchain with RUSTC_BOOTSTRAP=1 (the standard CI escape hatch)
# rather than depending on a nightly install. Library crates only — a
# binary-only crate has no public API and yields zero. Auto-trait impls
# (Send/Sync/Unpin/...) that cargo-public-api still lists even with --simplified
# are filtered out, leaving the crate's own declared public items (this also
# drops hand-written trait impls — a documented simplification).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_api comes from sourced tools.sh
require_tools rust api "${rust_tools_api[@]}"

target_dir="$(mktemp -d "${TMPDIR:-/tmp}/code-quality-measure.XXXXXX")"
trap 'rm -rf "$target_dir"' EXIT

# Unstable rustdoc JSON on stable, into a private target dir so we can find the
# single crate json deterministically. Success is inferred from the JSON file
# below, so a failing build is fine here (no lib target -> handled next).
RUSTC_BOOTSTRAP=1 cargo rustdoc --lib --manifest-path "$manifest" --target-dir "$target_dir" \
  -- -Z unstable-options --output-format json >/dev/null 2>&1 || true

json="$(find "$target_dir/doc" -maxdepth 1 -name '*.json' 2>/dev/null | head -1)"
if [ -z "$json" ]; then
  # No lib target (binary-only crate) or the crate did not build — no public API.
  echo "api: no rustdoc JSON produced (no lib target, or crate did not build)" >&2
  emit_json api rust '"count"' null '[]' '{"public_items": 0}'
  exit 0
fi

items="$(cargo-public-api --rustdoc-json "$json" --simplified 2>/dev/null | grep -vE '^impl ' || true)"
rows="$(jq -Rn '[inputs | select(length > 0) | {item: .}]' <<<"$items")"
summary="$(jq '{public_items: length}' <<<"$rows")"

emit_json api rust '"count"' null "$rows" "$summary"
