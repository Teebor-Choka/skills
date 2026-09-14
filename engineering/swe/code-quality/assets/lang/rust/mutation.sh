#!/usr/bin/env bash
# Mutation testing metric — cargo-mutants. Rewrites each function/operator in
# turn and reruns the test suite; a mutant the tests fail to catch ("missed")
# is a gap in test strength that line coverage can't reveal.
#
# This is by far the most expensive metric here — it rebuilds and reruns the
# whole test suite once per mutant — so run.sh keeps it OUT of the default
# `measure` sweep unless CODE_QUALITY_ENABLE_MUTATION is set. Run it directly
# for a one-off. On a large project bound it via CODE_QUALITY_MUTATION_ARGS
# (e.g. "--in-diff changes.diff" for changed lines only, or "-j 4" for
# parallelism); with no args it mutates the whole tree.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_mutation comes from sourced tools.sh
require_tools rust mutation "${rust_tools_mutation[@]}"

out_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
trap 'rm -rf "$out_dir"' EXIT

extra_args=()
# shellcheck disable=SC2206 # intentional word-split: caller passes flags like "-j 4"
[ -z "${CODE_QUALITY_MUTATION_ARGS:-}" ] || extra_args=(${CODE_QUALITY_MUTATION_ARGS})

# cargo-mutants exits nonzero when mutants survive or time out — a finding, not
# an error (like cargo-iceberg4rust's exit 2). So don't let set -e abort on it;
# trust the presence of a valid outcomes.json instead. Its own progress goes to
# stderr to keep our stdout pure JSON.
set +e
cargo mutants --manifest-path "$manifest" --output "$out_dir" "${extra_args[@]}" 1>&2
set -e

report="$out_dir/mutants.out/outcomes.json"
if [ ! -s "$report" ] || ! jq -e . >/dev/null 2>&1 <"$report"; then
  echo "mutation: cargo-mutants did not produce a valid outcomes.json" >&2
  exit 1
fi

# Rows are the survivors (missed mutants) — the actionable findings. Each
# outcome's scenario is a union ("Baseline" string vs {Mutant: {...}}); select
# only real mutants that were missed.
rows="$(jq '[.outcomes[]
  | select((.scenario | type) == "object" and .summary == "MissedMutant")
  | .scenario.Mutant
  | {file, line: .span.start.line, function: .function.function_name, change: .name}]' "$report")"

# score = killed / viable, guarding the all-unviable case (viable == 0), where
# cargo-mutants reports missed=0 and exits 0 — "passes having tested nothing".
summary="$(jq '{
  total_mutants, caught, missed, unviable, timeout,
  score: (if (.total_mutants - .unviable) > 0
          then (.caught / (.total_mutants - .unviable))
          else null end)
}' "$report")"

emit_json mutation rust '"score"' null "$rows" "$summary"
