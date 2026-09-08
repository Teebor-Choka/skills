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

metrics=(filerisk crap)
# shellcheck disable=SC2034 # read indirectly below via ${!tools_var}
tools_filerisk="cargo-iceberg4rust"
# shellcheck disable=SC2034 # read indirectly below via ${!tools_var}
tools_crap="cargo-llvm-cov cargo-crap"

# --- Phase 1: discovery ---
echo "== code-quality:measure discovery (rust) =="
available=()
for metric in "${metrics[@]}"; do
  tools_var="tools_${metric}"
  missing=()
  # shellcheck disable=SC2086 # intentional word-splitting of a space-separated tool list
  for tool in ${!tools_var}; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
  done
  if [ "${#missing[@]}" -eq 0 ]; then
    echo "  [available] $metric"
    available+=("$metric")
  else
    echo "  [missing]   $metric (needs: ${missing[*]}) -- see ../../references/rust.md"
  fi
done
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
