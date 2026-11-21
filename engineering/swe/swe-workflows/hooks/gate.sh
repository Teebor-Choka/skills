#!/usr/bin/env sh
# gate.sh — the portable enforcement guardrail every harness's native hook calls.
#
# A pre-action hook (Claude Code PreToolUse, oh-my-pi hooks/pre tool_call, OpenCode
# tool.execute.before, Codex hooks) passes the pending tool call's JSON on stdin. This reads it,
# and when the action is an integration boundary — a git commit, a PR/MR create-ready, or a
# merge/integrate — it asks the forge binding (forge-state.sh) whether that boundary's external
# condition actually holds (CI green + review clean, the red-first artifact), then runs
# policy-gate with --ok set accordingly. So in `mode: team` it BLOCKS only a genuinely unmet
# boundary — a green, reviewed merge passes without a manual override; in `mode: single` it
# warns and allows. Keeping the logic here (not in each overlay) keeps the four native wrappers
# thin and in sync.
#
# Exit codes: 0 allow or warn; 2 block (Claude Code blocks a tool call on exit 2 only; exit 1 is a non-blocking
# error there). A host with another convention wraps this script and maps 2.
#
# Env the overlay may set: SWE_REPO (repo root; default: $PWD), SWE_SKILL_DIR (this skill dir;
# default: derived from $0). SWE_GATE_OK=1 still forces a pass, for a caller that verified the
# condition out of band or a forge the binding cannot query.
set -eu

# The `implement` skill (which owns policy-gate.sh) is a sibling of this hooks/ dir.
SKILL_DIR=${SWE_SKILL_DIR:-"$(CDPATH='' cd -- "$(dirname -- "$0")/../skills/implement" && pwd)"}
REPO=${SWE_REPO:-"$PWD"}
GATE="$SKILL_DIR/scripts/policy-gate.sh"
[ -f "$GATE" ] || {
  echo "gate.sh: policy-gate not found at $GATE" >&2
  exit 0
} # fail open if unbundled

# Read the tool call (JSON) if any; tolerate empty stdin (some events pass args instead).
INPUT=""
if [ ! -t 0 ]; then INPUT=$(cat 2>/dev/null || true); fi

# Map the pending action to a boundary. boundary.py parses the payload and matches a boundary command
# only at the head of a command segment, so a commit message, heredoc body or `echo` that merely mentions
# `git merge` is not gated. A plain `git push` is NOT a boundary: pushing to a feature branch is how you
# iterate toward green. Only an actual merge integrates.
boundary=""
ref=""
if [ -n "$INPUT" ]; then
  found=$(printf '%s' "$INPUT" | python3 "$(dirname -- "$0")/boundary.py" 2>/dev/null || true)
  read -r boundary ref <<EOF || true
$found
EOF
fi
[ -n "$boundary" ] || exit 0 # not a guarded action

# The boundary maps to the gate whose policy it must satisfy.
case "$boundary" in
commit) gate=tdd ;;
ready) gate=review ;;
integrate) gate=integrate ;;
esac

# Decide whether the boundary's external condition holds, and pass --ok only when it does. The
# forge query lives in the binding (forge-state.sh) so policy-gate stays forge-neutral.
FORGE="$SKILL_DIR/scripts/forge-state.sh"
ok=""
if [ "${SWE_GATE_OK:-0}" = "1" ]; then
  ok="--ok" # caller asserts the condition out of band
elif [ -f "$FORGE" ]; then
  state=0
  if [ -n "$ref" ]; then
    sh "$FORGE" "$REPO" "$boundary" "$ref" || state=$?
  else
    sh "$FORGE" "$REPO" "$boundary" || state=$?
  fi
  case "$state" in
  0) ok="--ok" ;; # verified: CI green + reviewed, or the red-first artifact is present
  1) ok="" ;;     # genuinely unmet → policy-gate blocks (team) / warns (single)
  *)              # indeterminate (no gh / no PR / offline)
    case "$boundary" in
    integrate) ok="" ;; # never pass an unverified merge
    *)
      ok="--ok" # commit/ready: do not hard-block when state is not machine-checkable
      echo "gate.sh: $boundary state not verifiable; allowing (merge stays gated)" >&2
      ;;
    esac
    ;;
  esac
fi

# policy-gate exits 1 (block) in team mode without --ok, 0 (warn) in single. Claude Code blocks a tool
# call on exit 2 only (exit 1 is a non-blocking error), so a block exits 2 with the reason on stderr.
rc=0
if [ -n "$ok" ]; then
  sh "$GATE" "$REPO" gate "$gate" --ok || rc=$?
else
  sh "$GATE" "$REPO" gate "$gate" || rc=$?
fi
if [ "$rc" -ne 0 ]; then
  echo "gate.sh: $boundary blocked by policy (gate $gate); satisfy it or set SWE_GATE_OK=1 once verified" >&2
  exit 2
fi
