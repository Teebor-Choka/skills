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

manifest="${1:-pyproject.toml}"
project_dir="$(project_dir_of "$manifest")"

# shellcheck disable=SC2154 # python_tools_hotspots comes from sourced tools.sh
require_tools python hotspots "${python_tools_hotspots[@]}"

if ! is_churn_capable "$project_dir"; then
  echo "code-quality:measure/lang/python/hotspots: $project_dir isn't a full git working copy (or is a shallow clone) — churn history isn't available." >&2
  exit 3
fi

# One bulk complexipy run over the whole project (same approach cognitive.sh
# uses) rather than one process per touched file — a project with N touched
# files no longer means N tool invocations. Run from inside project_dir so
# complexipy's own "path" field comes out relative to it, matching
# churn_counts' paths below.
tmp_json="$(mktemp -t code-quality-measure.XXXXXX)"
trap 'rm -f "$tmp_json"' EXIT
(cd "$project_dir" && complexipy . --output-format json --output "$tmp_json" -q) >/dev/null 2>&1

declare -A complexity_by_file=()
while IFS=$'\t' read -r complexity path; do
  complexity_by_file["$path"]="$complexity"
done < <(jq -r 'group_by(.path) | map({path: .[0].path, complexity: (map(.complexity) | add)}) | .[] | [(.complexity | tostring), .path] | @tsv' "$tmp_json")

{
  echo -e "Hotspot\tTouches\tComplexity\tFile"
  while IFS=$'\t' read -r count path; do
    case "$path" in
    *.py) ;;
    *) continue ;;
    esac
    [ -f "$project_dir/$path" ] || continue
    complexity="${complexity_by_file[$path]:-0}"
    hotspot="$(awk -v c="$count" -v x="$complexity" 'BEGIN { printf "%.1f", c * x }')"
    echo -e "$hotspot\t$count\t$complexity\t$path"
  done < <(churn_counts "$project_dir")
} | (
  IFS=$'\t' read -r header
  echo "$header"
  sort -t $'\t' -k1,1 -rn
)
