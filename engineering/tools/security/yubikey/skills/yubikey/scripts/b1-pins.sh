#!/bin/sh
# B1: set the PINs on one key. Usage: b1-pins.sh LABEL
# ykman asks for each current and new PIN itself, so no PIN passes through this script.
. "$(dirname "$0")/lib.sh"
need_init
label=${1-}
[ -n "$label" ] || die "usage: b1-pins.sh LABEL"
role=$(label_role "$label")
[ -n "$role" ] || die "unknown label: $label"
ask_card "$label"
say "Factory defaults: User PIN 123456, Admin PIN 12345678. Use a different Admin PIN and Reset Code on every key."
say "Daily keys may share the User PIN. The root key gets its own."
confirm "Set the OpenPGP User PIN, Admin PIN and Reset Code on $label now?" || die "stopped"
yk openpgp access change-pin || die "User PIN change failed"
yk openpgp access change-admin-pin || die "Admin PIN change failed"
yk openpgp access change-reset-code || die "Reset Code change failed"
if [ "$role" = daily ]; then
  say "FIDO2 PIN for SSH (the same PIN on both daily keys is fine)."
  yk fido access change-pin || die "FIDO2 PIN change failed"
  say "The factory Yubico OTP in slot 1 types a long string on a stray touch. Remove it."
  if confirm "Delete OTP slot 1 on $label?"; then yk otp delete 1 || say "OTP delete did not run. Do it later: ykman otp delete 1"; fi
fi
yk openpgp info 2>/dev/null </dev/null | grep -e 'tries remaining' || true
mark_done "B1.$label"
