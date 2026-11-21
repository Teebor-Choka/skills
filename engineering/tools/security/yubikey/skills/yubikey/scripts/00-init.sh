#!/bin/sh
# Ask how many YubiKeys there are and name each one. Writes devices.tsv.
. "$(dirname "$0")/lib.sh"

if [ -s "$YKHK_STATE/devices.tsv" ]; then
  say "A device list already exists:"
  cat "$YKHK_STATE/devices.tsv"
  confirm "Discard it and start over?" || die "kept the existing list"
  rm -f "$YKHK_STATE"/devices.tsv "$YKHK_STATE"/done.*
fi

ask "How many YubiKeys will you set up?" 3
count=$REPLY
case $count in '' | *[!0-9]* | 0) die "count must be a whole number of 1 or more" ;; esac

tmp=$(mktemp)
i=1
while [ "$i" -le "$count" ]; do
  case $i in 1) drole=root dlabel=root ;; 2) drole=daily dlabel=nano ;; 3) drole=daily dlabel=nfc ;;
  *) drole=daily dlabel="daily$i" ;; esac
  ask "Key $i: role (root or daily)?" "$drole"
  role=$REPLY
  case $role in root | daily) ;; *) die "role must be root or daily" ;; esac
  ask "Key $i: short label?" "$dlabel"
  label=$REPLY
  case $label in '' | *[!a-z0-9-]*) die "label: lowercase letters, digits, hyphen only" ;; esac
  printf '%s\t%s\t%s\t-\t-\tno\n' "$i" "$role" "$label" >>"$tmp"
  i=$((i + 1))
done

roots=$(awk -F'\t' '$2=="root"' "$tmp" | wc -l | tr -d ' ')
[ "$roots" -eq 1 ] || {
  rm -f "$tmp"
  die "need exactly one root key, found $roots"
}

say ""
say "Plan:"
cat "$tmp"
confirm "Save this plan?" || {
  rm -f "$tmp"
  die "nothing saved"
}
mv "$tmp" "$YKHK_STATE/devices.tsv"
say ""
progress
