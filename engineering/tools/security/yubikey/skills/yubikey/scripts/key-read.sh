#!/bin/sh
# Non-interactive. Usage: key-read.sh LABEL
# Exactly one YubiKey must be plugged in. Records serial and firmware (verified=read).
. "$(dirname "$0")/lib.sh"
need_init
label=${1-}
[ -n "$label" ] || die "usage: key-read.sh LABEL"
awk -F'\t' -v l="$label" '$3==l {f=1} END {exit !f}' "$YKHK_STATE/devices.tsv" || die "unknown label: $label"
serials=$(yk list --serials 2>/dev/null </dev/null)
n=$(printf '%s' "$serials" | grep -c .)
[ "$n" -eq 1 ] || die "found $n YubiKeys. Plug in exactly one."
awk -F'\t' -v s="$serials" -v l="$label" '$4==s && $3!=l {bad=1} END {exit bad}' "$YKHK_STATE/devices.tsv" ||
  die "serial $serials is already recorded for another key"
fw=$(yk info 2>/dev/null </dev/null | awk -F': *' '/Firmware version/ {print $2; exit}')
[ -n "$fw" ] || die "could not read firmware"
ver_ge "$fw" "$YKHK_MIN_FW" || die "firmware $fw is below $YKHK_MIN_FW. Replace this key. Firmware cannot be updated."
tmp=$(mktemp)
awk -F'\t' -v OFS='\t' -v l="$label" -v s="$serials" -v f="$fw" '$3==l {$4=s; $5=f; $6="read"} 1' \
  "$YKHK_STATE/devices.tsv" >"$tmp" && mv "$tmp" "$YKHK_STATE/devices.tsv"
rm -f "$YKHK_STATE/done.A1" # a re-read puts the key back to "read": genuineness must be confirmed again
say "$label: serial $serials, firmware $fw (ok)"
