#!/usr/bin/env sh
# policy-context.sh — SessionStart hook: inject the repo's resolved .agents/policy as context, so
# every skill reads practices/gate/mode from these values instead of hardcoding a constant.
#
# Silent (exit 0, no output) when the policy loader or python3 is missing or the policy is
# malformed: it must never block a session. The loader is found by the same probe policy-gate
# uses (scripts/find-loader.sh), so it works wherever the harness installed `harness:policy`.
set -eu

FIND="$(CDPATH='' cd -- "$(dirname -- "$0")/../skills/implement/scripts" && pwd)/find-loader.sh"
command -v python3 >/dev/null 2>&1 || exit 0
LOADER=$(sh "$FIND" 2>/dev/null) || exit 0
policy=$(python3 "$LOADER" "${CLAUDE_PROJECT_DIR:-$PWD}" --json 2>/dev/null) || exit 0
[ -n "$policy" ] || exit 0

python3 - "$policy" <<'PY'
import json, sys
ctx = ("This repository's development policy (the .agents/policy format; see the `policy` skill) "
       "resolves to the JSON below. Skills read their configuration from these values rather than "
       "hardcoding a constant: interaction, grounding, gate, practices, mode, and per-file `files` "
       "rules. When a skill needs a key, use the value here (for a per-file setting apply the most "
       "specific `files` glob matching the file you are acting on), falling back to the skill's own "
       "default when a key is absent.\n\n" + sys.argv[1].strip())
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
PY
