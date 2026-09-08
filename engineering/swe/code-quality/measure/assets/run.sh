#!/usr/bin/env bash
# Language-agnostic entrypoint for code-quality:measure.
#
# Detects the target's language from marker files and execs the matching
# runner in this directory. Plain shell, no LLM/Claude dependency — a human,
# CI, or any other agent can call this exactly the way the skill does.
set -euo pipefail

dir="${1:-.}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$dir/Cargo.toml" ]; then
  exec "$script_dir/rust/run.sh" "$dir/Cargo.toml"
fi

echo "code-quality:measure: no runner for this project yet (checked: Cargo.toml)." >&2
echo "See ../SKILL.md — do not guess a tool chain for an unsupported language." >&2
exit 2
