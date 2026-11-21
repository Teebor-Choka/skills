#!/usr/bin/env sh
# forge-state.sh — the GitHub binding's state query for the swe-workflows gate.
#
# gate.sh calls this to learn whether a boundary's EXTERNAL condition holds right now, then
# passes --ok to policy-gate only when it does. Keeping the forge query here (not in
# policy-gate) is what lets policy-gate stay forge-neutral: swapping GitHub for GitLab/beads is
# swapping this one file (see references/bindings.md).
#
# Usage:  forge-state.sh <repo> <commit|ready|integrate> [pr-ref]
# Exit:   0  condition MET        — integrate: CI all green AND the PR is APPROVED
#         1  condition UNMET      — red/pending CI, not approved, or changes requested
#         2  INDETERMINATE        — no gh, not authed, no PR yet, or offline; caller decides
set -eu

REPO=${1:?usage: forge-state.sh <repo> <commit|ready|integrate> [pr-ref]}
BOUNDARY=${2:?usage: forge-state.sh <repo> <commit|ready|integrate> [pr-ref]}
REF=${3:-}

inrepo() { (CDPATH='' cd -- "$REPO" && "$@"); }

case "$BOUNDARY" in
commit)
  # The TDD red is a git artifact, not a forge fact — and at pre-commit time the pending commit
  # may itself BE the red test. So this never hard-fails (would block the red): MET if the
  # branch already carries a test-touching commit, else INDETERMINATE (gate.sh warns, allows).
  if inrepo git log --name-only --format= -n 50 2>/dev/null |
    grep -Eq '(^|/)(tests?|specs?|__tests__)/|(_test|_spec|\.test|\.spec)\.'; then
    exit 0
  fi
  exit 2
  ;;
ready)
  # Ready = the implementation is complete and feedback is requested. CI results and reviews are
  # that feedback; they arrive after ready and never gate it, so the forge has no say here.
  exit 2
  ;;
integrate)
  command -v gh >/dev/null 2>&1 || exit 2 # no forge reachable → caller decides

  # Resolve the PR: an explicit ref if the command carried one, else the current branch's.
  if [ -n "$REF" ]; then
    num=$(inrepo gh pr view "$REF" --json number -q .number 2>/dev/null) || num=""
  else
    num=$(inrepo gh pr view --json number -q .number 2>/dev/null) || num=""
  fi
  [ -n "$num" ] || exit 2 # no PR for the branch — nothing to check

  # CI must be fully green: `gh pr checks` exits 0 only when every check passed (8 = pending,
  # non-zero = failed/none). Anything but a clean pass is unmet.
  inrepo gh pr checks "$num" >/dev/null 2>&1 || exit 1

  # Review must be a positive approval with nothing requesting changes.
  dec=$(inrepo gh pr view "$num" --json reviewDecision -q .reviewDecision 2>/dev/null) || dec=""
  [ "$dec" = "APPROVED" ] || exit 1
  exit 0
  ;;
*)
  echo "forge-state: unknown boundary: $BOUNDARY (commit|ready|integrate)" >&2
  exit 2
  ;;
esac
