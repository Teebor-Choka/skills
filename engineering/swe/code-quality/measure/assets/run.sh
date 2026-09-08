#!/usr/bin/env bash
# Language-agnostic entrypoint for code-quality:measure.
#
# Takes a manifest path, not a directory — the caller decides where its
# manifest lives; this script doesn't opinionate about layout. Detects the
# language from the manifest's filename and execs the matching runner in
# this directory. Plain shell, no LLM/Claude dependency — a human, CI, or
# any other agent can call this exactly the way the skill does.
set -euo pipefail

manifest="${1:-Cargo.toml}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(basename "$manifest")" in
Cargo.toml)
  exec "$script_dir/rust/run.sh" "$manifest"
  ;;
esac

echo "code-quality:measure: no runner for this manifest yet ($manifest)." >&2
echo "See the code-quality:measure skill's SKILL.md — do not guess a tool chain" >&2
echo "for an unsupported language." >&2
exit 2
