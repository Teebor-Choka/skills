#!/bin/sh
# B7: touch policy, and PIN-once for signatures, on one key. Usage: b7-touch.sh LABEL
# The Admin PIN is read once and passed to ykman with -a (airgapped, non-adversarial: it shows in ps for a moment).
# The result is read back from the card, and the step fails on any mismatch.
. "$(dirname "$0")/lib.sh"
need_init
label=${1-}
[ -n "$label" ] || die "usage: b7-touch.sh LABEL"
role=$(label_role "$label")
[ -n "$role" ] || die "unknown label: $label"
ask_card "$label"
HAVE_A=0
yk openpgp keys set-touch --help 2>/dev/null </dev/null | grep -q -- '--admin-pin' && HAVE_A=1
adm() { if [ "$HAVE_A" -eq 1 ]; then yk "$@" -a "$SECRET"; else yk "$@"; fi; }
if [ "$HAVE_A" -eq 1 ]; then read_secret "Admin PIN of the $label key: "; else
  SECRET=
  say "This ykman has no --admin-pin: it asks per command."
fi
if [ "$role" = root ]; then
  adm openpgp keys set-touch sig on || {
    SECRET=
    die "set-touch sig failed"
  }
else
  adm openpgp keys set-touch sig cached || {
    SECRET=
    die "set-touch sig failed"
  }
  adm openpgp keys set-touch enc off || {
    SECRET=
    die "set-touch enc failed"
  }
  adm openpgp keys set-touch aut off || {
    SECRET=
    die "set-touch aut failed"
  }
  adm openpgp access set-signature-policy once || {
    SECRET=
    die "set-signature-policy failed"
  }
fi
SECRET=
unset SECRET
info=$(yk openpgp info </dev/null 2>&1) || die "could not read the card back"
pol=$(printf '%s\n' "$info" | awk '/Touch policy:/ {printf "%s ", $3}')
sigpin=$(printf '%s\n' "$info" | awk -F': *' '/Require PIN for signature/ {print $2}')
say "Touch policy (sig enc aut): $pol"
say "Signature PIN: $sigpin"
if [ "$role" = root ]; then
  case $pol in "On "*) ;; *) die "root signature touch policy is not On (read: $pol)" ;; esac
else
  [ "$pol" = "Cached Off Off " ] || die "daily touch policy is not Cached Off Off (read: $pol)"
  [ "$sigpin" = Once ] || die "signature PIN policy is not Once (read: $sigpin)"
fi
mark_done "B7.$label"
