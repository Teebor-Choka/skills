#!/usr/bin/env bash
# FileRisk metric — cargo-iceberg4rust, per package.
#
# cargo-iceberg4rust scores one package, not a virtual workspace root (it
# demands --package when the manifest resolves to more than one package). So we
# enumerate the workspace's member packages with `cargo metadata` and run it
# once per package, aggregating the per-file rows into one array — each row
# tagged with its package. A single-package project is just the one-member case.
#
# Pure static syn-AST analysis, no build/coverage — fanned out in parallel.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_filerisk comes from sourced tools.sh
require_tools rust filerisk "${rust_tools_filerisk[@]}"

# Workspace member packages as "name<TAB>manifest_path"; --no-deps limits this to
# the workspace's own members, and a single-package project yields exactly one.
mapfile -t members < <(
  cargo metadata --no-deps --format-version 1 --manifest-path "$manifest" |
    jq -r '.packages[] | [.name, .manifest_path] | @tsv'
)

rows="[]"
threshold="null"
failed=()
for entry in "${members[@]}"; do
  name="${entry%%$'\t'*}"
  mpath="${entry#*$'\t'}"
  # exit 2 = threshold crossed (a finding, not an error, per the tool's CI-gate
  # convention); any other nonzero is a real failure for that package — skip it
  # (recorded) but keep the rest, so one bad package doesn't lose the others.
  set +e
  raw="$(cargo iceberg4rust --manifest-path "$mpath" --package "$name" --json 2>/dev/null)"
  st=$?
  set -e
  if { [ "$st" -eq 0 ] || [ "$st" -eq 2 ]; } && jq -e . >/dev/null 2>&1 <<<"$raw"; then
    rows="$(jq -n --argjson acc "$rows" --arg pkg "$name" --argjson raw "$raw" '
      $acc + [$raw.files[] | {
        package: $pkg,
        file: .relative_file,
        risk: .risk_score,
        effective_loc,
        private_function_count,
        private_complexity_sum,
        data_struct_count: .data_private_struct_count,
        behavioral_struct_count: .behavioral_private_struct_count
      }]')"
    threshold="$(jq '.threshold' <<<"$raw")"
  else
    failed+=("$name")
  fi
done

[ "${#failed[@]}" -eq 0 ] ||
  echo "code-quality:measure/lang/rust/filerisk: cargo-iceberg4rust failed for: ${failed[*]}" >&2

rows="$(jq 'sort_by(-.risk)' <<<"$rows")"
summary="$(jq -n --argjson rows "$rows" --argjson pkgs "${#members[@]}" '{
  packages: $pkgs,
  scored_files: ($rows | length),
  total_risk: ([$rows[].risk] | add // 0)
}')"

emit_json filerisk rust '"score"' "$threshold" "$rows" "$summary"
