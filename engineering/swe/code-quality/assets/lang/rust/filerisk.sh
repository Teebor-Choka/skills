#!/usr/bin/env bash
# FileRisk metric — cargo-iceberg4rust.
#
# Standalone: pure static analysis, no coverage/build dependency, so this
# has no prerequisite chain of its own. Safe to run independently of the
# other metrics, and fanned out in parallel with them by run.sh.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_filerisk comes from sourced tools.sh
require_tools rust filerisk "${rust_tools_filerisk[@]}"

# cargo-iceberg4rust resolves --manifest-path via cargo_metadata, which
# reports the WHOLE workspace's package list even when pointed at one
# member's own manifest — so it demands --package whenever that workspace
# has more than one member, regardless of which manifest was passed. The
# member's own [package] name (read from its own manifest, not guessed) is
# the correct disambiguator; a workspace-root-only manifest has no
# [package] section at all, so there's genuinely nothing to derive and the
# tool's own error is left to surface as-is.
package_name=""
if grep -q '^\[package\]' "$manifest"; then
  package_name="$(awk -F'"' '/^\[package\]/{p=1; next} /^\[/{p=0} p && /^name[[:space:]]*=/{print $2; exit}' "$manifest")"
fi

args=(--manifest-path "$manifest" --json)
[ -n "$package_name" ] && args+=(--package "$package_name")

# Exits 2 (not 0) whenever anything crosses --threshold — a CI-gate
# convention, not a tool error. `set -e` would otherwise abort this script
# before printing anything on every real finding, which is exactly the
# case that matters — found by testing directly against a fixture designed
# to trigger a real finding, not caught by earlier "no findings" fixtures.
set +e
raw="$(cargo iceberg4rust "${args[@]}")"
status=$?
set -e
if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  echo "code-quality:measure/lang/rust/filerisk: cargo-iceberg4rust exited $status unexpectedly" >&2
  exit 1
fi

rows="$(jq '[.files[] | {
  file: .relative_file,
  risk: .risk_score,
  effective_loc,
  private_function_count,
  private_complexity_sum,
  data_struct_count: .data_private_struct_count,
  behavioral_struct_count: .behavioral_private_struct_count
}]' <<<"$raw")"
summary="$(jq '{scored_files, visible_files, total_risk}' <<<"$raw")"
threshold="$(jq '.threshold' <<<"$raw")"

emit_json filerisk rust '"score"' "$threshold" "$rows" "$summary"
