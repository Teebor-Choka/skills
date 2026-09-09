#!/usr/bin/env bash
# FileRisk metric — cargo-iceberg4rust.
#
# Standalone: pure static analysis, no coverage/build dependency, so this
# has no prerequisite chain of its own. Safe to run independently of the
# other metrics, and fanned out in parallel with them by run.sh.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_common.sh disable=SC1091
source "$script_dir/../_common.sh"
# shellcheck source=tools.sh disable=SC1091
source "$script_dir/tools.sh"

manifest="${1:-Cargo.toml}"

# shellcheck disable=SC2154 # rust_tools_filerisk comes from sourced tools.sh
require_tools rust filerisk "${rust_tools_filerisk[@]}"

# cargo-iceberg4rust resolves --manifest-path via cargo_metadata, which
# reports the WHOLE workspace's package list even when pointed at one
# member's own manifest — so it demands --package whenever that workspace
# has more than one member, regardless of which manifest was passed. The
# member's own [package] name (read from its own manifest, not guessed) is
# the correct disambiguator; a workspace-root-only manifest has no
# [package] section at all, so there's genuinely nothing to derive and the
# tool's own error is left to surface as-is.
package_name=""
if grep -q '^\[package\]' "$manifest"; then
  package_name="$(awk -F'"' '/^\[package\]/{p=1; next} /^\[/{p=0} p && /^name[[:space:]]*=/{print $2; exit}' "$manifest")"
fi

if [ -n "$package_name" ]; then
  cargo iceberg4rust --manifest-path "$manifest" --package "$package_name"
else
  cargo iceberg4rust --manifest-path "$manifest"
fi
