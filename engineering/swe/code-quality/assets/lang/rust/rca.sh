# shellcheck shell=bash
# Sourced, not executed. Shared by the Rust metrics that read
# rust-code-analysis-cli's per-file output — mi, halstead, loc, nom: they all
# need the same single bulk `-m -O json` run over the project and the same
# per-file root-node extraction, so that lives here once instead of in each.
# (cognitive.sh and hotspots.sh predate this and keep their own, more
# specialized extraction — cognitive walks nested function spaces, hotspots
# joins churn against per-file complexity.)

# Runs rust-code-analysis-cli once over <project_dir> and prints a JSON array
# of one object per source file: {file: <path relative to project_dir>,
# metrics: <that file's top-level metrics object>}. The tool's own progress
# chatter goes to stderr so stdout stays pure JSON.
#
# rust-code-analysis-cli emits null (not NaN/Inf) for a metric it can't
# compute on a given file — e.g. MI or Halstead difficulty on a file with no
# operands — so the JSON stays valid and callers pass those nulls straight
# through rather than needing to sanitize NaN out.
rca_root_metrics() {
  local project_dir="$1" out_dir
  out_dir="$(mktemp -d "${TMPDIR:-/tmp}/code-quality-measure.XXXXXX")"
  # -p needs an absolute path alongside -o or the tool silently analyzes
  # nothing (see cognitive.sh); callers resolve it with project_dir_of.
  rust-code-analysis-cli -m -p "$project_dir" -O json -o "$out_dir" -w 1>&2
  find "$out_dir" -name '*.json' -exec cat {} + | jq -s --arg prefix "$project_dir/" '
    [ .[] | { file: (.name | ltrimstr($prefix)), metrics: .metrics } ]'
  rm -rf "$out_dir"
}
