#!/usr/bin/env bash
# I/A/D metric — Robert C. Martin's Instability/Abstractness/Distance from
# the Main Sequence (Agile Software Development: Principles, Patterns, and
# Practices, 2002), via pyscn.
#
# No Rust equivalent: no verified tool computes these formulas for Rust (see
# references/rust.md's Known limitation) — this script has no rust/ sibling.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-pyproject.toml}"
project_dir="$(cd "$(dirname "$manifest")" && pwd)"

# shellcheck disable=SC2154 # python_tools_iad comes from sourced tools.sh
missing="$(missing_tools "${python_tools_iad[@]}")"
if [ "$missing" != "[]" ]; then
  echo "code-quality:measure/lang/python/iad: missing required tools: $missing" >&2
  echo "See the code-quality:measure skill's references/python.md for how to add" >&2
  echo "them." >&2
  exit 3
fi

# pyscn's own progress/summary output goes to stderr; --output - routes the
# JSON report to stdout instead of a .pyscn/reports/ file.
pyscn analyze --json --output - --skip-clones "$project_dir" 2>/dev/null | jq -r '
  .system.dependency_analysis.module_metrics // {}
  | to_entries
  | (["Module", "Ca", "Ce", "I", "A", "D"],
     (.[] | [.key, (.value.afferent_coupling|tostring), (.value.efferent_coupling|tostring),
             (.value.instability|tostring), (.value.abstractness|tostring), (.value.distance|tostring)]))
  | @tsv
'
