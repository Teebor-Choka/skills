# shellcheck shell=bash
# Sourced, not executed. Single source of truth for each metric's required
# tools — used by run.sh's discovery phase and by each metric script's own
# standalone tool-presence check (metric scripts stay independently
# callable, per their own header comments).

# shellcheck disable=SC2034 # used by run.sh/filerisk.sh/crap.sh, which source this file
tools_filerisk=(cargo-iceberg4rust)
# shellcheck disable=SC2034
tools_crap=(cargo-llvm-cov cargo-crap)

# Prints the space-separated subset of the given tool names that are not on
# PATH. Empty output means all are present.
missing_tools() {
  local tool missing=()
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
  done
  [ "${#missing[@]}" -eq 0 ] || echo "${missing[*]}"
}
