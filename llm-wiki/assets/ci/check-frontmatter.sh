#!/usr/bin/env sh
# check-frontmatter.sh — every wiki/**/*.md must have valid YAML frontmatter
# Required keys: title, type, domain, status
# Allowed type values: source-note concept entity moc synthesis
# Allowed status values: raw summarized synthesized
# Exit 0 = pass, non-zero = violations found

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIKI="$REPO_ROOT/wiki"
ERRORS=0

TYPES="source-note concept entity moc synthesis topic"
STATUSES="raw summarized synthesized"

check_key() {
  file="$1"; key="$2"
  if ! awk '/^---/{f++} f==1 && /^'"$key"':/' "$file" | grep -q .; then
    echo "MISSING key '$key': $file"
    return 1
  fi
  return 0
}

check_enum() {
  file="$1"; key="$2"; allowed="$3"
  value=$(awk '/^---/{f++} f==1 && /^'"$key"':/{print}' "$file" | sed "s/^$key: *//;s/['\"]//g;s/ *#.*//" | tr -d ' ')
  for v in $allowed; do
    [ "$value" = "$v" ] && return 0
  done
  echo "INVALID $key '$value' (allowed: $allowed): $file"
  return 1
}

has_frontmatter() {
  file="$1"
  # First non-empty line must be ---
  first=$(awk 'NF{print; exit}' "$file")
  [ "$first" = "---" ]
}

find "$WIKI" -name "*.md" | sort | while IFS= read -r f; do
  file_ok=1

  if ! has_frontmatter "$f"; then
    echo "NO FRONTMATTER: $f"
    file_ok=0
  else
    for key in title type domain status; do
      check_key "$f" "$key" || file_ok=0
    done
    check_enum "$f" "type" "$TYPES" || file_ok=0
    check_enum "$f" "status" "$STATUSES" || file_ok=0
  fi

  [ "$file_ok" = "1" ] || ERRORS=$((ERRORS + 1))
done

# Count errors from subshell
error_count=$(find "$WIKI" -name "*.md" | sort | while IFS= read -r f; do
  fail=0
  has_frontmatter "$f" || { fail=1; }
  if has_frontmatter "$f"; then
    for key in title type domain status; do
      check_key "$f" "$key" 2>/dev/null || fail=1
    done
    check_enum "$f" "type" "$TYPES" 2>/dev/null || fail=1
    check_enum "$f" "status" "$STATUSES" 2>/dev/null || fail=1
  fi
  [ "$fail" = "1" ] && echo x
done | wc -l | tr -d ' ')

if [ "$error_count" -gt 0 ]; then
  echo "check-frontmatter: $error_count file(s) failed"
  exit 1
fi
echo "check-frontmatter: OK"
