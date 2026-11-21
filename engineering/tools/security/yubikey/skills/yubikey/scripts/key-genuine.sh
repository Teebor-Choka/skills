#!/bin/sh
# Non-interactive. Usage: key-genuine.sh LABEL
# Call after the user confirmed the Yubico genuineness page. Marks A1 done when every key is verified.
. "$(dirname "$0")/lib.sh"
need_init
label=${1-}
[ -n "$label" ] || die "usage: key-genuine.sh LABEL"
awk -F'\t' -v l="$label" '$3==l && $6=="read" {f=1} END {exit !f}' "$YKHK_STATE/devices.tsv" ||
  die "$label has no recorded serial. Run key-read.sh first."
tmp=$(mktemp)
awk -F'\t' -v OFS='\t' -v l="$label" '$3==l {$6="yes"} 1' "$YKHK_STATE/devices.tsv" >"$tmp" && mv "$tmp" "$YKHK_STATE/devices.tsv"
say "$label: genuine, verified."
if awk -F'\t' '$6!="yes" {bad=1} END {exit bad}' "$YKHK_STATE/devices.tsv"; then mark_done A1; fi
progress
