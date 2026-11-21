#!/usr/bin/env bash
# Public API surface metric — cargo-public-api over rustdoc JSON, per library
# package. rustdoc documents one crate; a virtual workspace root has no lib
# target of its own, so we enumerate the workspace's library packages via
# `cargo metadata` and run rustdoc + cargo-public-api once per package,
# aggregating the public items into one array (each tagged with its package). A
# single-package project is just the one-member case; a binary-only project
# yields zero.
#
# rustdoc JSON is an unstable format that normally needs a nightly toolchain;
# RUSTC_BOOTSTRAP=1 unlocks it on the stable toolchain (the standard CI escape
# hatch). Auto-trait/blanket impls that cargo-public-api still lists even with
# --simplified are filtered out, leaving each crate's own declared public items.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_api comes from sourced tools.sh
require_tools rust api "${rust_tools_api[@]}"

# Library packages as "name<TAB>crate", where crate is the lib target's name
# rustdoc emits JSON under ('-' -> '_'). Only packages with a lib target have a
# public API; binaries are skipped.
mapfile -t libs < <(
  cargo metadata --no-deps --format-version 1 --manifest-path "$manifest" |
    jq -r '.packages[] as $p | $p.targets[]
             | select(.kind | index("lib"))
             | [$p.name, (.name | gsub("-"; "_"))] | @tsv'
)

target_dir="$(mktemp -d "${TMPDIR:-/tmp}/code-quality-measure.XXXXXX")"
trap 'rm -rf "$target_dir"' EXIT

rows="[]"
failed=()
for entry in "${libs[@]}"; do
  name="${entry%%$'\t'*}"
  crate="${entry#*$'\t'}"
  # Success is inferred from the JSON file below, so a failing build is fine.
  # --manifest-path anchors `-p` to this workspace (not the caller's cwd).
  RUSTC_BOOTSTRAP=1 cargo rustdoc -p "$name" --lib \
    --manifest-path "$manifest" --target-dir "$target_dir" \
    -- -Z unstable-options --output-format json >/dev/null 2>&1 || true
  json="$target_dir/doc/$crate.json"
  [ -f "$json" ] || {
    failed+=("$name")
    continue
  }
  items="$(cargo-public-api --rustdoc-json "$json" --simplified 2>/dev/null | grep -vE '^impl ' || true)"
  rows="$(jq -Rn --argjson acc "$rows" --arg pkg "$name" \
    '$acc + [inputs | select(length > 0) | {package: $pkg, item: .}]' <<<"$items")"
done

[ "${#failed[@]}" -eq 0 ] || echo "api: no rustdoc JSON produced for: ${failed[*]}" >&2

summary="$(jq -n --argjson rows "$rows" --argjson libs "${#libs[@]}" \
  '{library_packages: $libs, public_items: ($rows | length)}')"

emit_json api rust '"count"' null "$rows" "$summary"
