#!/usr/bin/env sh
# policy-gate — resolve the repo's .agents/policy and gate a workflow step by it.
#
# The `implement` skill (and a commit/ready/integrate hook) calls this at each gate so policy
# is enforced as data, not trusted to the implementer. It locates the `policy` skill's loader,
# resolves practices/gate/mode, prints what the named gate REQUIRES, and sets its exit code by
# `mode`: in `team` an unverified gate BLOCKS (exit 1); in `single` it WARNS (exit 0). This
# script stays forge-neutral: it does NOT query CI or the review bot. The caller verifies the
# external condition (gate.sh does it through the forge binding, forge-state.sh) and passes
# --ok when it holds; without --ok a team-mode gate blocks.
#
# Usage:
#   policy-gate.sh <repo> show [--target FILE]
#   policy-gate.sh <repo> gate <spec|tdd|quality|review|integrate> [--target FILE] [--ok]
#
# --ok : the caller asserts the gate's external condition passed. Without it, a team-mode
#        gate blocks (exit 1).
set -eu

die() {
  echo "policy-gate: $*" >&2
  exit 2
}
[ $# -ge 2 ] || die "usage: policy-gate.sh <repo> show|gate <name> [--target FILE] [--ok]"

REPO=$1
CMD=$2
shift 2
NAME=""
TARGET=""
OK=0
if [ "$CMD" = "gate" ]; then
  [ $# -ge 1 ] || die "gate needs a name: spec|tdd|quality|review|integrate"
  NAME=$1
  shift
fi
while [ $# -gt 0 ]; do
  case "$1" in
  --target)
    TARGET=${2:?--target needs a file}
    shift 2
    ;;
  --ok)
    OK=1
    shift
    ;;
  *) die "unknown arg: $1" ;;
  esac
done

# Locate the policy skill's loader (shared probe: installed skill dirs, then this source tree).
LOADER=$(sh "$(dirname -- "$0")/find-loader.sh" 2>/dev/null) || LOADER=""
[ -n "$LOADER" ] || die "policy_loader.py not found (install the 'harness' plugin, harness:policy, or set AGENTS_POLICY_LOADER)"

get() { # key default
  _t=""
  [ -n "$TARGET" ] && _t="--target $TARGET"
  # shellcheck disable=SC2086
  python3 "$LOADER" "$REPO" --get "$1" $_t 2>/dev/null || printf '%s' "$2"
}

PRACTICES=$(get practices '')
# This workflow's default discipline when policy is silent: ATDD at the boundary, TDD at the
# unit. A repo opts out or changes it via `practices` in its .agents/policy.
case "$PRACTICES" in '' | '{}') PRACTICES='scope: ATDD, task: TDD' ;; esac
GATE=$(get gate plain)
MODE=$(get mode single)

if [ "$CMD" = "show" ]; then
  printf 'practices=%s\ngate=%s\nmode=%s\n' "$PRACTICES" "$GATE" "$MODE"
  exit 0
fi

# Requirement text per gate, derived from the resolved policy.
case "$NAME" in
spec) REQ="work item carries acceptance criteria (valid inputs, 'done', failure behaviour)" ;;
tdd) case "$PRACTICES" in *TDD*) REQ="a functional failing test is committed before the implementation (red ran and failed on behaviour, not compilation)" ;; *) REQ="(practices.task is not TDD — no red-first artifact required)" ;; esac ;;
quality) REQ="the project's quality gate passes (gate=$GATE); else the quality skill named in policy reports no unresolved finding" ;;
review) REQ="an isolated adversarial review and the external review bot are clean (gate=$GATE)" ;;
integrate) REQ="all green: CI + automated review clean, then integrate per the merge policy (mode=$MODE)" ;;
*) die "unknown gate: $NAME (spec|tdd|quality|review|integrate)" ;;
esac

echo "gate:$NAME requires: $REQ"

# Decide block vs warn. --ok means the caller verified the external condition.
if [ "$OK" -eq 1 ]; then
  exit 0
fi
case "$MODE" in
team)
  echo "policy-gate: BLOCK (mode=team) — verify the condition and re-run with --ok" >&2
  exit 1
  ;;
*)
  echo "policy-gate: WARN (mode=single) — proceeding; confirm the condition held" >&2
  exit 0
  ;;
esac
