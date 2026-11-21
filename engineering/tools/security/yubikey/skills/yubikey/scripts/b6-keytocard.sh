#!/bin/sh
# B6: move the primary key from RAM to the root card. Irreversible: the RAM copy goes, the card cannot export it.
# Refuses until the restore test (B5) passed.
. "$(dirname "$0")/lib.sh"
need_init
use_gnupghome
need_fpr
need_done B5
root=$(root_label)
[ -n "$root" ] || die "no root key in devices.tsv"
need_done "B1.$root"
ask_card "$root"
cs=$(gpg --card-status 2>/dev/null)
attrs() { printf '%s\n' "$cs" | awk -F': *' '/^Key attributes/ {print $2; exit}' | awk '{print $1}'; }
if [ "$(attrs)" != ed25519 ]; then
  say "The root card's Signature slot is '$(attrs)'. Set it to Curve25519 first:"
  say "    admin   then   key-attr   then pick ECC and Curve 25519 for the Signature slot, Admin PIN, then quit"
  confirm "Open gpg --card-edit now?" || die "stopped"
  gpg --card-edit
  cs=$(gpg --card-status 2>/dev/null)
  [ "$(attrs)" = ed25519 ] || die "the Signature slot is still '$(attrs)'"
fi
say ""
say "Point of no return. Both backups restored in B5. In the gpg menu:"
say "    keytocard   then   y   then choose the Signature key slot   then   save"
say "    windows: the primary passphrase (names your key), then the root key's Admin PIN. Read each title."
say "    use  abc  in the passphrase window to show what you typed."
confirm "Move the primary key to $root now?" || die "stopped"
gpg --edit-key "$KEYFPR"
sk=$(gpg -K "$KEYFPR" 2>/dev/null)
printf '%s\n' "$sk" | grep -q '^sec>' || die "the primary key is not on the card (no sec>). Do not rerun keytocard. Read gpg -K."
say "Primary key is on the root card:"
printf '%s\n' "$sk" | sed -n 1,3p
mark_done B6
