#!/usr/bin/env sh
# check-layout.sh — structural invariants:
#   1. wiki/ contains only .md files (no images, binaries, code)
#   2. unsorted/ does not exist
# Exit 0 = pass, non-zero = violations found.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIKI="$REPO_ROOT/wiki"
ERRORS=0

# 1. wiki/ must contain only .md files
non_md=$(find "$WIKI" -type f ! -name "*.md" ! -name ".DS_Store" 2>/dev/null)
if [ -n "$non_md" ]; then
  echo "NON-MARKDOWN files in wiki/:"
  printf '%s\n' "$non_md"
  ERRORS=$((ERRORS + 1))
fi

# 2. unsorted/ must not exist
if [ -d "$REPO_ROOT/unsorted" ]; then
  echo "DIRECTORY unsorted/ still exists (should be dissolved)"
  ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
  echo "check-layout: $ERRORS violation(s)"
  exit 1
fi
echo "check-layout: OK"
