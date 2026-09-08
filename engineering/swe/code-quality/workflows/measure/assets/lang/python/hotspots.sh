#!/usr/bin/env bash
# Hotspots metric — git commit churn x cognitive complexity, joined per file.
#
# Same shape as rust/hotspots.sh (churn_counts() lives in ../_common.sh,
# shared by both) — only the per-file complexity source differs.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"
project_dir="$(cd "$(dirname "$manifest")" && pwd)"

# shellcheck disable=SC2154 # python_tools_hotspots comes from sourced tools.sh
missing="$(missing_tools "${python_tools_hotspots[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/python/hotspots: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/python.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

if ! is_churn_capable "$project_dir"; then
  echo "code-quality:measure/lang/python/hotspots: $project_dir isn't a full git working copy (or is a shallow clone) — churn history isn't available." >&2
  exit 3
fi

tmp_json="$(mktemp -t code-quality-measure.XXXXXX)"
trap 'rm -f "$tmp_json"' EXIT

{
  echo -e "Hotspot\tTouches\tComplexity\tFile"
  while IFS=$'\t' read -r count path; do
    case "$path" in
    *.py) ;;
    *) continue ;;
    esac
    [ -f "$project_dir/$path" ] || continue
    complexipy "$project_dir/$path" --output-format json --output "$tmp_json" -q >/dev/null 2>&1
    complexity="$(jq '[.[].complexity] | add // 0' "$tmp_json")"
    hotspot="$(awk -v c="$count" -v x="$complexity" 'BEGIN { printf "%.1f", c * x }')"
    echo -e "$hotspot\t$count\t$complexity\t$path"
  done < <(churn_counts "$project_dir")
} | (
  IFS=$'\t' read -r header
  echo "$header"
  sort -t $'\t' -k1,1 -rn
)
