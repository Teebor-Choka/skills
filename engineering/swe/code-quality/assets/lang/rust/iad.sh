#!/usr/bin/env bash
# I/A/D metric (Rust) — Robert C. Martin's Instability/Abstractness/Distance
# from the Main Sequence (Agile Software Development: Principles, Patterns,
# and Practices, 2002), per crate, via cargo-anatomy. Each workspace crate is
# a "package"; each type (struct/enum/trait/type) a "class", with traits
# counted as the abstract ones (A = traits / total types). The Python sibling
# (lang/python/iad.sh) computes the same metric via pyscn.
#
# Pure static syn-AST + cargo_metadata analysis — no build or coverage step,
# so it fans out in parallel with the other metrics like filerisk does. Only
# workspace member crates appear in cargo-anatomy's default output (external
# dependency crates are not scored), so every row is a crate you own. This is
# crate-level coupling; intra-crate module-level coupling has no verified Rust
# tool (see references/rust.md).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_iad comes from sourced tools.sh
require_tools rust iad "${rust_tools_iad[@]}"

# cargo-anatomy prints its JSON report to stdout by default; kept on stdout
# (not redirected away) so a failure surfaces its own message here instead of
# a downstream jq parse error with no context — same handling as the Python
# sibling.
raw="$(cargo anatomy --manifest-path "$manifest")"

if ! jq -e . >/dev/null 2>&1 <<<"$raw"; then
  echo "iad: cargo-anatomy did not produce valid JSON on stdout:" >&2
  echo "$raw" >&2
  exit 1
fi

# i/a/d come out as clean floats even for a crate with zero types (N=0):
# cargo-anatomy yields a=0, i=0, d=|0+0-1|/√2 rather than a NaN from the 0/0,
# verified directly against such a crate — so no NaN sanitizing is needed here
# the way rust-code-analysis's MI/Halstead would.
rows="$(jq '[.crates[] | {
  crate: .crate_name,
  ca: .metrics.ca,
  ce: .metrics.ce,
  instability: .metrics.i,
  abstractness: .metrics.a,
  distance: .metrics.d
}]' <<<"$raw")"
summary="$(jq '{crates: length}' <<<"$rows")"

emit_json iad rust null null "$rows" "$summary"
