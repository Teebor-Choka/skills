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

# By default cargo-anatomy scores only workspace member crates (external
# dependency crates are excluded), so every row is a crate you own. That
# under-reports coupling for a project whose members couple mainly to sibling
# crates published in OTHER workspaces (verified on a real multi-workspace
# repo: its members showed sparse intra-workspace Ca/Ce, but --include-external
# with a scope prefix surfaced the ecosystem coupling). Set
# CODE_QUALITY_IAD_EXTERNAL_SCOPE to one or more comma-separated cargo-anatomy
# scope selectors (e.g. "pkg-prefix:hopr") to widen the graph to matching
# external crates; unset = members only. The selector syntax is
# cargo-anatomy's own (pkg:/pkg-prefix:/crate:/crate-prefix:/dep:).
scope="${CODE_QUALITY_IAD_EXTERNAL_SCOPE:-}"
err_file="$(mktemp)"
trap 'rm -f "$err_file"' EXIT

if [ -n "$scope" ]; then
  set +e
  raw="$(cargo anatomy --manifest-path "$manifest" --include-external --external-scope "$scope" 2>"$err_file")"
  status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    # A scope that matches no external crate is a hard error in cargo-anatomy,
    # not empty output — which would abort a whole `measure` run over a project
    # that legitimately has no matching external dependency. Degrade to the
    # members-only view (with a note) for that specific case only; any other
    # failure still surfaces.
    if grep -q "no external crates matched" "$err_file"; then
      echo "iad: no external crate matched CODE_QUALITY_IAD_EXTERNAL_SCOPE='$scope' for $manifest — falling back to workspace members only" >&2
      raw="$(cargo anatomy --manifest-path "$manifest")"
    else
      cat "$err_file" >&2
      echo "iad: cargo-anatomy failed (external-scope='$scope')" >&2
      exit 1
    fi
  fi
else
  # kept on stdout (not redirected away) so a failure surfaces its own message
  # here rather than as a downstream jq parse error with no context — same
  # handling as the Python sibling.
  raw="$(cargo anatomy --manifest-path "$manifest")"
fi

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
