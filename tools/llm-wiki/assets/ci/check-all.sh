#!/usr/bin/env sh
# check-all.sh — run all wiki invariant checks
# Exit 0 = all pass, non-zero = one or more failed.
# Used as the pre-commit hook and CI gate.

set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

run_check() {
  script="$1"
  if sh "$script"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
}

run_check "$DIR/check-frontmatter.sh"
run_check "$DIR/check-links.sh"
run_check "$DIR/check-orphans.sh"
run_check "$DIR/check-layout.sh"
run_check "$DIR/check-log.sh"

echo ""
echo "Results: $PASS passed, $FAIL failed"

[ "$FAIL" -eq 0 ]
