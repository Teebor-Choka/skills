#!/bin/sh
# B3: put sign, encrypt and authenticate subkeys on one daily card. Usage: b3-subkeys.sh LABEL
# The gpg menus stay interactive: their numbering differs between GnuPG versions. This script prints what
# to pick, then checks the result: three subkeys on the card, each with an expiry.
. "$(dirname "$0")/lib.sh"
need_init
use_gnupghome
need_fpr
need_done B2
label=${1-}
[ -n "$label" ] || die "usage: b3-subkeys.sh LABEL"
[ "$(label_role "$label")" = daily ] || die "$label is not a daily key"
need_done "B1.$label" # PINs change before any key material goes on the card
ask_card "$label"

# One gpg --card-status per look: each run starts or polls scdaemon (up to a second).
cs=$(gpg --card-status 2>/dev/null)
attrs() { printf '%s\n' "$cs" | awk -F': *' '/^Key attributes/ {print $2; exit}'; }
holds_keys() { printf '%s\n' "$cs" | grep -E '^(Signature|Encryption|Authentication) key' | grep -vq '\[none\]'; }
if holds_keys; then die "$label already holds OpenPGP keys. Changing key attributes would delete them. Stop and check."; fi

if [ "$(attrs)" != "ed25519 cv25519 ed25519" ]; then
  say "Key attributes are '$(attrs)'. Set all three slots to Curve25519. In the gpg menu:"
  say "    admin   then   key-attr"
  say "    for Signature, Encryption and Authentication: choose the entry that reads ECC, then Curve 25519"
  say "    the Admin PIN window comes first. Then:   quit"
  confirm "Open gpg --card-edit now?" || die "stopped"
  gpg --card-edit
  cs=$(gpg --card-status 2>/dev/null)
  [ "$(attrs)" = "ed25519 cv25519 ed25519" ] || die "key attributes are still '$(attrs)'. Redo key-attr."
fi

ask "Subkey validity for $label (for example 1y or 2y)?" "${YKHK_EXPIRY:-1y}"
period=$REPLY
valid_period "$period" || die "bad validity: $period (use 1y, 18m, 90d or a date; zero and never are not allowed)"
say ""
say "In the gpg menu, three times (Signature key, Encryption key, Authentication key):"
say "    addcardkey   then pick that key type, validity: $period"
say "    windows: one titled just PIN asks the OpenPGP User PIN; the one naming your key asks the primary passphrase."
say "    read each title before you type. Finish with:   save"
confirm "Open gpg --edit-key now?" || die "stopped"
gpg --edit-key "$KEYFPR"

fprs=$(card_fprs)
n=$(printf '%s\n' "$fprs" | grep -c .)
[ "$n" -eq 3 ] || die "the card reports $n subkey fingerprints, expected 3. Run gpg --card-status and read it."
tbl=$(subkey_table)
missing=""
for f in $fprs; do
  line=$(printf '%s\n' "$tbl" | awk -v f="$f" '$1==f')
  [ -n "$line" ] || die "card key $f is not in the ceremony keyring. Did gpg save?"
  case $line in *" "?*) ;; *) missing="$missing $f" ;; esac
done
if [ -n "$missing" ]; then
  say "These subkeys have no expiry:$missing"
  confirm "Set $period on them now (primary passphrase window follows)?" || die "no expiry set. Fix before B4: subkey-expiry.sh $period$missing"
  # shellcheck disable=SC2086
  g --quick-set-expire "$KEYFPR" "$period" $missing || die "setting the expiry failed"
fi
# shellcheck disable=SC2086 # the fingerprints are separate words
printf '%s\n' $fprs | tr '\n' ' ' >"$YKHK_STATE/card.$label"
echo >>"$YKHK_STATE/card.$label"
say "$label subkeys: $(cat "$YKHK_STATE/card.$label")"
mark_done "B3.$label"
