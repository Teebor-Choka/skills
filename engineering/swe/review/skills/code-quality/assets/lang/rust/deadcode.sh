#!/usr/bin/env bash
# Dead-code metric — rustc's own dead_code/unused_* lints via
# `cargo check --message-format=json`. No new tool. Rows are each such
# diagnostic (file/line/lint/message). Note rustc never flags a `pub` item as
# dead_code, so a genuinely-unused public API won't appear here — pair with the
# module-tree "orphans" view if that matters (see references/rust.md).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_deadcode comes from sourced tools.sh
require_tools rust deadcode "${rust_tools_deadcode[@]}"

# cargo check exits 0 even with warnings; a hard compile error exits nonzero
# and yields no useful dead-code data (e.g. offline with unfetched deps), which
# we surface rather than silently reporting "no dead code".
set +e
raw="$(cargo check --manifest-path "$manifest" --message-format=json 2>/dev/null)"
status=$?
set -e

rows="$(jq -s '[.[]
  | select(.reason == "compiler-message")
  | .message
  | select(.code.code != null and (.code.code == "dead_code" or (.code.code | startswith("unused_"))))
  | { file: (.spans[0].file_name // null), line: (.spans[0].line_start // null), lint: .code.code, message: .message }]' <<<"$raw" 2>/dev/null || echo '[]')"

if [ "$status" -ne 0 ] && [ "$(jq 'length' <<<"$rows")" -eq 0 ]; then
  echo "deadcode: cargo check exited $status with no diagnostics — the crate may not build (e.g. offline with unfetched deps)" >&2
  exit 1
fi

summary="$(jq '{findings: length}' <<<"$rows")"

emit_json deadcode rust null null "$rows" "$summary"
