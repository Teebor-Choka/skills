#!/usr/bin/env bash
# Hotspots metric — git commit churn x cognitive complexity, joined per file.
# See ../shared/hotspots.sh for why this join exists instead of a dedicated tool.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=../shared/hotspots.sh disable=SC1091
source "$script_dir/../shared/hotspots.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"
project_dir="$(project_dir_of "$manifest")"

# shellcheck disable=SC2154 # rust_tools_hotspots comes from sourced tools.sh
require_tools rust hotspots "${rust_tools_hotspots[@]}"

if ! is_churn_capable "$project_dir"; then
  echo "code-quality:measure/lang/rust/hotspots: $project_dir isn't a full git working copy (or is a shallow clone) — churn history isn't available." >&2
  exit 3
fi

# One bulk rust-code-analysis-cli run over the whole project (same approach
# cognitive.sh uses) rather than one process per touched file — a project
# with N touched files no longer means N tool invocations.
tmp_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
trap 'rm -rf "$tmp_dir"' EXIT
rust-code-analysis-cli -m -p "$project_dir" -O json -o "$tmp_dir" -w 1>&2

declare -A cognitive_by_file=()
while IFS=$'\t' read -r cognitive path; do
  cognitive_by_file["$path"]="$cognitive"
done < <(find "$tmp_dir" -name '*.json' -exec cat {} + | jq -s -r --arg prefix "$project_dir/" '
  .[] | [(.metrics.cognitive.sum // 0 | tostring), (.name | ltrimstr($prefix))] | @tsv
')

{
  echo -e "Hotspot\tTouches\tCognitive\tFile"
  while IFS=$'\t' read -r count path; do
    case "$path" in
    *.rs) ;;
    *) continue ;;
    esac
    [ -f "$project_dir/$path" ] || continue
    cognitive="${cognitive_by_file[$path]:-0}"
    hotspot="$(awk -v c="$count" -v x="$cognitive" 'BEGIN { printf "%.1f", c * x }')"
    echo -e "$hotspot\t$count\t$cognitive\t$path"
  done < <(churn_counts "$project_dir")
} | (
  IFS=$'\t' read -r header
  echo "$header"
  sort -t $'\t' -k1,1 -rn
)
