#!/usr/bin/env bash
# Hotspots metric — git commit churn x cognitive complexity, joined per file.
#
# Not a single external tool: this is the same manual join Adam Tornhill's
# own code-maat documents (its README joins a `revisions` analysis against a
# separately-computed complexity source by hand, since code-maat itself only
# measures churn). churn_counts() lives in ../_common.sh, shared with
# python/hotspots.sh; the complexity half reuses this language's own
# cognitive-complexity tool per touched file rather than trusting a second
# output format.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"
project_dir="$(cd "$(dirname "$manifest")" && pwd)"

# shellcheck disable=SC2154 # rust_tools_hotspots comes from sourced tools.sh
missing="$(missing_tools "${rust_tools_hotspots[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/rust/hotspots: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/rust.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

if ! is_churn_capable "$project_dir"; then
  echo "code-quality:measure/lang/rust/hotspots: $project_dir isn't a full git working copy (or is a shallow clone) — churn history isn't available." >&2
  exit 3
fi

{
  echo -e "Hotspot\tTouches\tCognitive\tFile"
  while IFS=$'\t' read -r count path; do
    case "$path" in
    *.rs) ;;
    *) continue ;;
    esac
    [ -f "$project_dir/$path" ] || continue
    cognitive="$(rust-code-analysis-cli -m -p "$project_dir/$path" -O json 2>/dev/null | jq '.metrics.cognitive.sum // 0')"
    hotspot="$(awk -v c="$count" -v x="$cognitive" 'BEGIN { printf "%.1f", c * x }')"
    echo -e "$hotspot\t$count\t$cognitive\t$path"
  done < <(churn_counts "$project_dir")
} | (
  IFS=$'\t' read -r header
  echo "$header"
  sort -t $'\t' -k1,1 -rn
)
