#!/bin/sh
# Read-only: assert the plugged-in card holds the state a finished step should have left. No PIN, no write.
# Usage: assert-card.sh MARKER   (B1.label, B3.label, B6, B7.label, B8.label; any other step holds no card: SKIP)
# go.sh runs it after each card step. Exit 1 on any FAIL.
. "$(dirname "$0")/lib.sh"
need_init
mark=${1-}
case $mark in
B1.* | B3.* | B7.* | B8.*) label=${mark#*.} ;;
B6) label=$(root_label) ;;
*)
  say "SKIP $mark: no card to check"
  exit 0
  ;;
esac
want=$(label_serial "$label")
[ -n "$want" ] && [ "$want" != - ] || die "unknown label or no serial recorded: $label"
role=$(label_role "$label")
fail=0
chk() { if [ "$2" = "$3" ]; then say "PASS $1: $3"; else
  say "FAIL $1: got '$3', want '$2'"
  fail=1
fi; }
got=$(yk list --serials 2>/dev/null </dev/null)
chk "key $label (serial)" "$want" "$got"
[ "$got" = "$want" ] || exit 1
info=$(yk openpgp info </dev/null 2>&1)
pol=$(printf '%s\n' "$info" | awk '/Touch policy:/ {printf "%s ", $3}')
case $mark in
B1.*)
  tries=$(printf '%s\n' "$info" | awk -F': *' '/tries remaining/ {printf "%s ", $2}')
  chk "PIN counters (user reset admin)" "3 3 3 " "$tries"
  ;;
B3.*)
  use_gnupghome
  recorded=$(tr -s ' \n' ' ' <"$YKHK_STATE/card.$label" 2>/dev/null | sed 's/ $//')
  chk "card subkeys" "$recorded" "$(card_fprs | tr '\n' ' ' | sed 's/ $//')"
  ;;
B6)
  need_fpr
  chk "primary key on the card" "$KEYFPR" "$(card_fprs | head -n 1)"
  ;;
B7.*)
  if [ "$role" = root ]; then
    chk "signature touch" On "$(printf '%s' "$pol" | awk '{print $1}')"
  else
    chk "touch policy (sig enc aut)" "Cached Off Off " "$pol"
    chk "signature PIN" Once "$(printf '%s\n' "$info" | awk -F': *' '/Require PIN for signature/ {print $2}')"
  fi
  ;;
B8.*)
  free=$(yk fido info </dev/null 2>&1 | awk '/Credential storage remaining/ {print $NF}')
  if [ "${free:-100}" -lt 100 ]; then say "PASS FIDO2 credential stored (storage free: $free)"; else
    say "FAIL no FIDO2 credential stored"
    fail=1
  fi
  ;;
esac
exit $fail
