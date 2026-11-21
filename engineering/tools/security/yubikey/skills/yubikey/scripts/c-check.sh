#!/bin/sh
# Mac side, read-only, no PIN: check the one plugged-in key against the plan and the ceremony record.
# Usage: c-check.sh [RECORD]   (default /Volumes/PUBLIC/ceremony-record.txt). Exit 1 on any FAIL.
# A daily key needs a card(label) line in the record, so plug in the PUBLIC stick or pass a copy. The card must also hold
# subkeys of the key imported by c-import.sh, so run that first.
. "$(dirname "$0")/lib.sh"
need_init
rec=${1:-/Volumes/PUBLIC/ceremony-record.txt}
serials=$(yk list --serials 2>/dev/null </dev/null)
n=$(printf '%s' "$serials" | grep -c .)
[ "$n" -eq 1 ] || die "found $n YubiKeys. Plug in exactly one."
label=$(awk -F'\t' -v s="$serials" '$4==s {print $3}' "$YKHK_STATE/devices.tsv")
[ -n "$label" ] || die "serial $serials is not in devices.tsv"
role=$(label_role "$label")
fail=0
chk() { if [ "$2" = "$3" ]; then say "PASS $1: $3"; else
  say "FAIL $1: got '$3', want '$2'"
  fail=1
fi; }
info=$(yk openpgp info </dev/null 2>&1)
tries=$(printf '%s\n' "$info" | awk -F': *' '/tries remaining/ {printf "%s ", $2}')
chk "PIN counters (user reset admin)" "3 3 3 " "$tries"
pol=$(printf '%s\n' "$info" | awk '/Touch policy:/ {printf "%s ", $3}')
if [ "$role" = root ]; then
  chk "signature touch" On "$(printf '%s' "$pol" | awk '{print $1}')"
else
  chk "touch policy (sig enc aut)" "Cached Off Off " "$pol"
  chk "signature PIN" Once "$(printf '%s\n' "$info" | awk -F': *' '/Require PIN for signature/ {print $2}')"
  fi_info=$(yk fido info </dev/null 2>&1)
  chk "FIDO2 PIN attempts" 8 "$(printf '%s\n' "$fi_info" | awk '/^PIN:/ {print $2}')"
  free=$(printf '%s\n' "$fi_info" | awk '/Credential storage remaining/ {print $NF}')
  if [ "${free:-100}" -lt 100 ]; then
    say "PASS FIDO2 credential stored (storage free: $free)"
  else
    say "FAIL no FIDO2 credential stored"
    fail=1
  fi
  # An installed SSH key must be a FIDO2 key. A plain software key swapped in for a handle is not one.
  sshpub="$HOME/.ssh/id_ed25519_sk_$label.pub"
  if [ -f "$sshpub" ]; then
    sshl=$(ssh-keygen -l -f "$sshpub" 2>/dev/null)
    case $sshl in
    *"(ED25519-SK)") say "PASS SSH key $label is a FIDO2 key: $(printf '%s' "$sshl" | awk '{print $2}')" ;;
    *)
      say "FAIL SSH key $label is not an ED25519-SK key: ${sshl:-unreadable}"
      fail=1
      ;;
    esac
  else
    say "SKIP no SSH key $sshpub installed yet"
  fi
  # The record must vouch for this card. A missing record or card line fails: it must not read as a pass.
  want=$(awk -v l="$label" '$1=="card(" l "):" {print $2, $3, $4}' "$rec" 2>/dev/null)
  if [ -n "$want" ]; then
    cf=$(card_fprs)
    got=$(printf '%s\n' "$cf" | tr '\n' ' ' | sed 's/ $//')
    chk "card subkeys match the record" "$want" "$got"
    # The record sits on the writable stick, so it cannot vouch alone. The card must also hold subkeys of the key that
    # c-import.sh imported under your paper fingerprint, which is the only key with ultimate trust that the record names.
    primary=$(awk '/^primary:/ {print $2; exit}' "$rec")
    if [ -n "$primary" ] && gpg --export-ownertrust 2>/dev/null | grep -q "^$primary:6:"; then
      keyset=$(gpg --with-colons --list-keys --with-subkey-fingerprints "$primary" 2>/dev/null | awk -F: '/^sub:/ {s=1; next} /^fpr:/ && s {print $10; s=0}')
      inkeys=yes
      [ "$(printf '%s\n' "$cf" | grep -c .)" -eq 3 ] || inkeys=no
      for f in $cf; do printf '%s\n' "$keyset" | grep -qx "$f" || inkeys=no; done
      chk "card subkeys belong to the imported identity" yes "$inkeys"
    else
      say "FAIL the record's primary key is not imported and trusted on this machine: run c-import.sh with your paper fingerprint first"
      fail=1
    fi
  else
    say "FAIL no card($label) line in $rec: the record cannot vouch for this key"
    fail=1
  fi
fi
if [ "$fail" -eq 0 ]; then
  say "$label (serial $serials): all checks passed"
else
  say "$label (serial $serials): FAILED"
  exit 1
fi
