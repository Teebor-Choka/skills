#!/usr/bin/env bash
# code-quality:report — human-readable view of code-quality:measure's JSON.
#
# Depends on measure: this script's whole job is running assets/run.sh and
# formatting its output, not computing anything itself. measure's own
# stdout stays pure JSON (see run.sh's own header comment) because agents
# are its primary consumer; report exists for the secondary case — a human
# watching a terminal — without measure's own output having to serve both
# audiences from one format. Deterministic, like measure: no LLM involved.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lang/_common.sh disable=SC1091
source "$script_dir/lang/_common.sh"

if [ "$#" -eq 0 ]; then
  echo "usage: report.sh <manifest-path> [<manifest-path> ...]" >&2
  exit 2
fi

# measure's own exit code reflects whether every job succeeded — capture it
# without letting `set -e` abort before this script can still render
# whatever measure DID produce (partial results are still worth showing).
set +e
json="$("$script_dir/run.sh" "$@")"
status=$?
set -e

echo "== code-quality:measure discovery =="
jq -r '.discovery.available[] | "  [available] " + .' <<<"$json"
jq -r '.discovery.missing[] | "  [missing]   " + .label + " (needs: " + (.needs | tostring) + ")"' <<<"$json"

echo
echo "== code-quality:measure summary =="
jq -r '.results | keys[]' <<<"$json" | while IFS= read -r label; do
  echo
  echo "--- $label ---"
  render_human "$(jq --arg k "$label" '.results[$k]' <<<"$json")"
done

exit "$status"
