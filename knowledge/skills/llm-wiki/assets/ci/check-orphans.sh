#!/usr/bin/env sh
# check-orphans.sh — every wiki page must be linked from its domain _MOC.md.
# Uses POSIX ERE (grep -E) — works on macOS BSD grep and GNU grep.
# Exit 0 = pass, non-zero = orphans found.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIKI="$REPO_ROOT/wiki"

ORPHAN_FILE=$(mktemp /tmp/ci_orphans.XXXXXX)

find "$WIKI" -name "*.md" | sort | while IFS= read -r f; do
  stem=$(basename "$f" .md)

  # MOC pages are the roots — never orphans
  [ "$stem" = "_MOC" ] && continue

  # Find the domain (first subdirectory under wiki/)
  rel="${f#"$WIKI"/}"
  domain=$(printf '%s' "$rel" | cut -d'/' -f1)
  moc="$WIKI/$domain/_MOC.md"

  if [ ! -f "$moc" ]; then
    printf 'MISSING MOC for domain %s: %s\n' "$domain" "$f"
    echo x >>"$ORPHAN_FILE"
    continue
  fi

  # Check that [[stem]] or [[stem| or [[Domain/stem]] appears in the MOC.
  # Use word-boundary: stem must be followed by ]] or | (not more slug chars).
  if ! grep -iE "\[\[($domain/)?$stem(\||\]\])" "$moc" >/dev/null 2>&1; then
    printf 'ORPHAN (not in _MOC.md): %s\n' "$f"
    echo x >>"$ORPHAN_FILE"
  fi
done

orphan_count=$(wc -l <"$ORPHAN_FILE" | tr -d ' ')
rm -f "$ORPHAN_FILE"

if [ "$orphan_count" -gt 0 ]; then
  echo "check-orphans: $orphan_count orphan(s)"
  exit 1
fi
echo "check-orphans: OK"
