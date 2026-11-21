#!/usr/bin/env bash
# Usage: render-hooks.sh <plugin-dir>
# Render <plugin-dir>/hooks/manifest.json to <plugin-dir>/hooks/hooks.json with agent-env's
# renderClaudeHooks, taken from this flake's pinned agent-env input. Output is `jq -S` sorted.
set -euo pipefail

dir="${1:-}"
if [ -z "$dir" ]; then
  echo "usage: render-hooks.sh <plugin-dir>" >&2
  exit 2
fi
if [ ! -f "$dir/hooks/manifest.json" ]; then
  echo "render-hooks: $dir/hooks/manifest.json not found" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dir="$(cd "$dir" && pwd)"

# shellcheck disable=SC2016  # the ${} below is Nix, not shell
out="$(
  REPO="$repo" MANIFEST="$dir/hooks/manifest.json" nix eval --json --impure --expr '
    let
      f = builtins.getFlake "path:${builtins.getEnv "REPO"}";
      l = import "${f.inputs.agent-env}/modules/home/agent-plugins-lib.nix" { inherit (f.inputs.nixpkgs) lib; };
    in
    l.renderClaudeHooks (builtins.fromJSON (builtins.readFile (builtins.getEnv "MANIFEST")))
  '
)"
printf '%s\n' "$out" | jq -S . >"$dir/hooks/hooks.json"
echo "wrote $dir/hooks/hooks.json"
