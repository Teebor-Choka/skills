#!/bin/sh
# Terminal wrapper (own terminal or Tails): asks, then calls the non-interactive steps.
. "$(dirname "$0")/lib.sh"
need_init
D=$(dirname "$0")
URL=https://www.yubico.com/genuine/
# A for loop, not a pipe into while: die must end this script, and in a pipe it ends only the subshell.
for label in $(unverified_labels); do
  say ""
  say "=== $label ==="
  confirm "Is the packaging sealed and intact?" || die "do not use this key. Report it to the seller."
  until pause "Unplug all YubiKeys, then plug in ONLY the $label key" && sh "$D/key-read.sh" "$label"; do
    confirm "Try again?" || die "stopped"
  done
  say "Open $URL in a normal browser and touch the key when it blinks."
  { command -v open >/dev/null 2>&1 && open "$URL"; } || { command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL"; } || true
  confirm "Did the page report a genuine YubiKey?" || {
    reset_label "$label"
    die "key not genuine. Do not use it. Its row is reset."
  }
  sh "$D/key-genuine.sh" "$label" >/dev/null
  say "$label verified. Unplug it."
done
sh "$D/progress.sh"
