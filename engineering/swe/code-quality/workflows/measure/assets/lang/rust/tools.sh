# shellcheck shell=bash
# Sourced, not executed. Declares each Rust metric's required tools —
# language-prefixed so this can be sourced alongside other languages'
# tools.sh in the same process (assets/run.sh does exactly that for
# multi-language projects) with no naming collision, even where two
# languages happen to share a metric name (both Rust and Python have "crap").
# missing_tools() itself lives in ../_common.sh, not here.

# shellcheck disable=SC2034 # read by assets/run.sh's case-dispatch, not by name lookup in this file
rust_tools_filerisk=(cargo-iceberg4rust)
# shellcheck disable=SC2034
rust_tools_crap=(cargo-llvm-cov cargo-crap)
# shellcheck disable=SC2034
rust_tools_cognitive=(rust-code-analysis-cli)
# shellcheck disable=SC2034
rust_tools_hotspots=(rust-code-analysis-cli jq)
# shellcheck disable=SC2034
rust_tools_duplication=(jscpd)
