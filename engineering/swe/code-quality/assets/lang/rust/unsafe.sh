#!/usr/bin/env bash
# Unsafe-density metric — a textual count of the `unsafe` keyword per .rs file
# (word-boundary grep). Deliberately crude and dependency-free: it counts the
# keyword wherever it appears, including in comments or strings (a documented
# caveat), as a cheap first-party unsafe signal. For dependency-tree unsafe
# accounting use cargo-geiger instead — flaky on complex workspaces, see
# references/rust.md. Rows are only files that contain unsafe.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_unsafe comes from sourced tools.sh
require_tools rust unsafe "${rust_tools_unsafe[@]}"

project_dir="$(project_dir_of "$manifest")"

# -o one match per line, -H with filename; count occurrences per file. Skip
# build artifacts and git internals. No matches is not an error here (grep
# exits 1), so don't let set -e abort.
matches="$(grep -rHoE '\bunsafe\b' "$project_dir" --include='*.rs' \
  --exclude-dir=target --exclude-dir=.git 2>/dev/null || true)"

if [ -z "$matches" ]; then
  rows='[]'
else
  rows="$(awk -F: -v prefix="$project_dir/" '
    $0 == "" { next }
    {
      f = $1
      if (substr(f, 1, length(prefix)) == prefix) f = substr(f, length(prefix) + 1)
      count[f]++
    }
    END { for (k in count) print count[k] "\t" k }
  ' <<<"$matches" | jq -R 'split("\t") | {file: .[1], unsafe: (.[0] | tonumber)}' | jq -s 'sort_by(-.unsafe)')"
fi

summary="$(jq '{files_with_unsafe: length, total_unsafe: (map(.unsafe) | add // 0)}' <<<"$rows")"

emit_json unsafe rust '"count"' null "$rows" "$summary"
