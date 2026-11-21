#!/usr/bin/env bash
# Module fan-in/out metric — cargo-modules dependency graph. Rolls the
# item-level "uses" edges up to their owning modules: fan_out(M) = distinct
# modules M depends on, fan_in(M) = distinct modules depending on M. Cross-module
# "uses" edges only (intra-module use isn't coupling). cargo-modules emits a
# Graphviz DOT graph (no JSON), parsed with color disabled.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_fanio comes from sourced tools.sh
require_tools rust fanio "${rust_tools_fanio[@]}"

project_dir="$(project_dir_of "$manifest")"

# NO_COLOR keeps the DOT free of ANSI escapes (there is no --no-color flag).
# A failed analysis just yields no edges below, so tolerate a nonzero exit.
dot="$(cd "$project_dir" && NO_COLOR=1 cargo modules dependencies 2>/dev/null)" || true

# Module nodes: a node whose label kind (before the "|") is `mod` or `crate`.
# `|| true` guards pipefail when a grep legitimately matches nothing.
modules="$({ grep -E '\[label="' <<<"$dot" | grep -vF -- '->' |
  sed -E 's/^[[:space:]]*"([^"]+)" \[label="([^"]*)".*/\1\t\2/' |
  awk -F'\t' '$2 ~ /mod\|/ || $2 ~ /^crate\|/ { print $1 }'; } || true)"

# "uses" edges as "src<TAB>dst".
edges="$({ grep -F -- '->' <<<"$dot" | grep -F 'label="uses"' |
  sed -E 's/^[[:space:]]*"([^"]+)" -> "([^"]+)".*/\1\t\2/'; } || true)"

# Roll each edge's endpoints up to their owning module (the node itself if it is
# a module, else its parent path), then count distinct cross-module edges.
rows_tsv="$(awk -F'\t' '
  function owner(x) { if (x in mod) return x; p = x; sub(/::[^:]+$/, "", p); return p }
  FNR == NR { if ($1 != "") mod[$1] = 1; next }
  {
    s = owner($1); d = owner($2)
    if (s != d && s != "" && d != "") {
      k = s SUBSEP d
      if (!(k in seen)) { seen[k] = 1; fanout[s]++; fanin[d]++ }
    }
  }
  END { for (m in mod) print m "\t" (fanin[m] + 0) "\t" (fanout[m] + 0) }
' <(printf '%s\n' "$modules") <(printf '%s\n' "$edges"))"

rows="$(jq -Rn '[inputs | select(length > 0) | split("\t") | {module: .[0], fan_in: (.[1] | tonumber), fan_out: (.[2] | tonumber)}] | sort_by(-(.fan_in + .fan_out), .module)' <<<"$rows_tsv")"
summary="$(jq '{modules: length}' <<<"$rows")"

emit_json fanio rust null null "$rows" "$summary"
