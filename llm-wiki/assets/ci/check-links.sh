#!/usr/bin/env sh
# check-links.sh — every [[Target]] wikilink in wiki/**/*.md must resolve
# to an existing wiki page (matched by filename stem, case-insensitive).
# Uses POSIX ERE (grep -E) — works on macOS BSD grep and GNU grep.
# Exit 0 = pass, non-zero = broken links found.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIKI="$REPO_ROOT/wiki"

# Build a lookup file of all page stems (lowercase, no extension)
# Includes both wiki/ pages and raw/ source files (links to raw/ sources are valid)
STEMS_FILE=$(mktemp /tmp/ci_stems.XXXXXX)
find "$WIKI" "$REPO_ROOT/raw" -type f \( -name "*.md" -o -name "*.txt" \) 2>/dev/null | while IFS= read -r f; do
  # Strip extension and lowercase the basename
  base=$(basename "$f")
  stem="${base%.*}"
  printf '%s\n' "$stem" | tr '[:upper:]' '[:lower:]' | tr ' ' '-'
done > "$STEMS_FILE"

# Normalize a wikilink target to a page stem for lookup:
#   - Strip path prefix (raw/foo.md -> foo.md, Domain/slug -> slug)
#   - Strip file extension if present (.md, .txt)
#   - Lowercase, spaces to hyphens
normalize() {
  printf '%s' "$1" \
    | sed 's|.*/||' \
    | sed 's/\.[a-zA-Z]*$//' \
    | tr '[:upper:]' '[:lower:]' \
    | tr ' ' '-'
}

resolve() {
  norm=$(normalize "$1")
  grep -qx "$norm" "$STEMS_FILE"
}

BROKEN_FILE=$(mktemp /tmp/ci_broken.XXXXXX)

find "$WIKI" -name "*.md" | sort | while IFS= read -r f; do
  # Extract [[Target]] and [[Target|Display]] — grab content between [[ and ]] or |
  # Using sed to extract wikilink content: find [[ then capture until ] or |
  grep -oE '\[\[[^]|]+' "$f" 2>/dev/null | sed 's/^\[\[//' | while IFS= read -r target; do
    if ! resolve "$target"; then
      printf 'BROKEN LINK [[%s]]: %s\n' "$target" "$f"
      echo x >> "$BROKEN_FILE"
    fi
  done
done

broken_count=$(wc -l < "$BROKEN_FILE" | tr -d ' ')
rm -f "$STEMS_FILE" "$BROKEN_FILE"

if [ "$broken_count" -gt 0 ]; then
  echo "check-links: $broken_count broken link(s)"
  exit 1
fi
echo "check-links: OK"
