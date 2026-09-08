#!/usr/bin/env bash
# Rust orchestrator for code-quality:measure.
#
# Three phases, all deterministic — no LLM involved:
#   1. Discovery — checks which metrics have their required tools on PATH,
#      prints a minireport before anything runs.
#   2. Fan-out — each available metric runs as its own independent process,
#      in parallel with the others (see crap.sh for the one metric that
#      isn't internally independent: CRAP needs a coverage pass first).
#   3. Summary — every branch's report, printed together.
set -euo pipefail

manifest="${1:-Cargo.toml}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

# --- Phase 1: discovery ---
echo "== code-quality:measure discovery (rust) =="
available=()
check_metric() {
  local metric="$1" missing
  shift
  missing="$(missing_tools "$@")"
  if [ -z "$missing" ]; then
    echo "  [available] $metric"
    available+=("$metric")
  else
    echo "  [missing]   $metric (needs: $missing) -- see ../../references/rust.md"
  fi
}
# shellcheck disable=SC2154 # tools_filerisk/tools_crap come from sourced tools.sh
check_metric filerisk "${tools_filerisk[@]}"
# shellcheck disable=SC2154
check_metric crap "${tools_crap[@]}"
echo

if [ "${#available[@]}" -eq 0 ]; then
  echo "code-quality:measure/rust: no metric tools available, nothing to run." >&2
  exit 3
fi

# --- Phase 2: fan-out ---
tmp_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
trap 'rm -rf "$tmp_dir"' EXIT

pids=()
for metric in "${available[@]}"; do
  "$script_dir/$metric.sh" "$manifest" >"$tmp_dir/$metric.out" 2>"$tmp_dir/$metric.err" &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=1
done

# --- Phase 3: summary ---
echo "== code-quality:measure summary (rust) =="
for metric in "${available[@]}"; do
  echo
  echo "--- $metric ---"
  cat "$tmp_dir/$metric.out"
  if [ -s "$tmp_dir/$metric.err" ]; then
    echo "--- $metric (stderr) ---" >&2
    cat "$tmp_dir/$metric.err" >&2
  fi
done

exit "$status"
