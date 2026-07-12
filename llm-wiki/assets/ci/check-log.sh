#!/usr/bin/env sh
# check-log.sh — log.md must have at least one correctly-prefixed entry
# Format: ## [YYYY-MM-DD] <op> | <subject>
# Exit 0 = pass, non-zero = no valid entries found.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$REPO_ROOT/log.md"

if [ ! -f "$LOG" ]; then
  echo "MISSING log.md"
  exit 1
fi

count=$(grep -c "^## \[[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\]" "$LOG" || true)

if [ "$count" -lt 1 ]; then
  echo "check-log: no valid entries found in log.md (need '## [YYYY-MM-DD] op | subject')"
  exit 1
fi
echo "check-log: OK ($count entries)"
