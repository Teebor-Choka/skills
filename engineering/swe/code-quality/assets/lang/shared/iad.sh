# shellcheck shell=bash
# Sourced, not executed. The general I/A/D metric — Robert C. Martin's
# Instability/Abstractness/Distance from the Main Sequence (Agile Software
# Development: Principles, Patterns, and Practices, 2002). One metric with one
# output contract (rows of {<unit>, ca, ce, instability, abstractness,
# distance} + a count summary); only the tool that computes it and the shape
# of that tool's JSON differ by language, so that is the sole per-language
# part — a dispatch inside emit_iad_json. rust/iad.sh and python/iad.sh are
# thin wrappers that check their own tool's presence and delegate here, the
# same shape as duplication.sh.
#
# Tools: Rust -> cargo-anatomy (per crate; each type is a Martin "class",
# traits the abstract ones); Python -> pyscn (per module). Both are static
# analysis with no build/coverage step, so this fans out in parallel like
# filerisk.

# Runs cargo-anatomy for <manifest> and prints its JSON. By default it scores
# only workspace member crates (external dependency crates are excluded), so
# every row is a crate you own. That under-reports coupling for a project
# whose members couple mainly to sibling crates published in OTHER workspaces
# (verified on a real multi-workspace repo: members-only showed sparse
# intra-workspace Ca/Ce, but --include-external with a scope prefix surfaced
# the ecosystem coupling). Set CODE_QUALITY_IAD_EXTERNAL_SCOPE to one or more
# comma-separated cargo-anatomy scope selectors (pkg:/pkg-prefix:/crate:/
# crate-prefix:/dep:, e.g. "pkg-prefix:hopr") to widen the graph to matching
# external crates; unset = members only.
_iad_run_cargo_anatomy() {
  local manifest="$1" scope="${CODE_QUALITY_IAD_EXTERNAL_SCOPE:-}" err_file status raw
  if [ -z "$scope" ]; then
    cargo anatomy --manifest-path "$manifest"
    return
  fi

  err_file="$(mktemp)"
  set +e
  raw="$(cargo anatomy --manifest-path "$manifest" --include-external --external-scope "$scope" 2>"$err_file")"
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    rm -f "$err_file"
    printf '%s' "$raw"
    return
  fi

  # A scope that matches no external crate is a hard error in cargo-anatomy,
  # not empty output — which would abort a whole `measure` run over a project
  # that legitimately has no matching external dependency. Degrade to the
  # members-only view (with a note) for that specific case only; any other
  # failure still surfaces.
  if grep -q "no external crates matched" "$err_file"; then
    echo "iad: no external crate matched CODE_QUALITY_IAD_EXTERNAL_SCOPE='$scope' for $manifest — falling back to workspace members only" >&2
    rm -f "$err_file"
    cargo anatomy --manifest-path "$manifest"
    return
  fi
  cat "$err_file" >&2
  rm -f "$err_file"
  echo "iad: cargo-anatomy failed (external-scope='$scope')" >&2
  return 1
}

# Runs <language>'s I/A/D tool against <manifest> and prints this metric's
# canonical envelope (see ../_common.sh's emit_json). All metric-level
# structure lives here; each case arm only names the tool and reshapes its
# own JSON into the shared row schema.
emit_iad_json() {
  local language="$1" manifest="$2" raw rows summary

  case "$language" in
  rust)
    raw="$(_iad_run_cargo_anatomy "$manifest")"
    require_json "$raw" "iad: cargo-anatomy"
    # i/a/d come out as clean floats even for a crate with zero types (N=0):
    # cargo-anatomy yields a=0, i=0, d=|0+0-1|/√2 rather than a NaN from the
    # 0/0, verified directly — so no NaN sanitizing is needed here the way
    # rust-code-analysis's MI/Halstead would.
    rows="$(jq '[.crates[] | {
      crate: .crate_name,
      ca: .metrics.ca,
      ce: .metrics.ce,
      instability: .metrics.i,
      abstractness: .metrics.a,
      distance: .metrics.d
    }]' <<<"$raw")"
    summary="$(jq '{crates: length}' <<<"$rows")"
    ;;
  python)
    # pyscn's own progress/summary output normally goes to stderr; --output -
    # routes the JSON report to stdout instead of a .pyscn/reports/ file.
    raw="$(pyscn analyze --json --output - --skip-clones "$(project_dir_of "$manifest")")"
    require_json "$raw" "iad: pyscn"
    rows="$(jq '[.system.dependency_analysis.module_metrics // {} | to_entries[] | {
      module: .key,
      ca: .value.afferent_coupling,
      ce: .value.efferent_coupling,
      instability: .value.instability,
      abstractness: .value.abstractness,
      distance: .value.distance
    }]' <<<"$raw")"
    summary="$(jq '{modules: length}' <<<"$rows")"
    ;;
  *)
    echo "iad: no tool dispatch for language '$language'" >&2
    return 2
    ;;
  esac

  emit_json iad "$language" null null "$rows" "$summary"
}
