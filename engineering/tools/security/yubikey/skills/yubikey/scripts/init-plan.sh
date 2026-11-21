#!/bin/sh
# Non-interactive. Usage: init-plan.sh [--reset] COUNT [LABEL:ROLE ...]
# Without LABEL:ROLE pairs: key 1 = root, 2 = nano, 3 = nfc, more = daily4, daily5, ...
. "$(dirname "$0")/lib.sh"
if [ "${1-}" = --reset ]; then
  rm -f "$YKHK_STATE"/devices.tsv "$YKHK_STATE"/done.*
  shift
fi
[ ! -s "$YKHK_STATE/devices.tsv" ] || die "a plan exists. Pass --reset to discard it."
count=${1-}
[ $# -gt 0 ] && shift
case $count in '' | *[!0-9]* | 0) die "usage: init-plan.sh [--reset] COUNT [LABEL:ROLE ...]" ;; esac
tmp=$(mktemp)
i=1
while [ "$i" -le "$count" ]; do
  if [ $# -ge 1 ]; then
    label=${1%%:*}
    role=${1#*:}
    shift
  else
    case $i in 1) label=root role=root ;; 2) label=nano role=daily ;; 3) label=nfc role=daily ;;
    *) label=daily$i role=daily ;; esac
  fi
  case $role in root | daily) ;; *)
    rm -f "$tmp"
    die "role must be root or daily: $role"
    ;;
  esac
  case $label in '' | *[!a-z0-9-]*)
    rm -f "$tmp"
    die "bad label: $label"
    ;;
  esac
  printf '%s\t%s\t%s\t-\t-\tno\n' "$i" "$role" "$label" >>"$tmp"
  i=$((i + 1))
done
[ "$(awk -F'\t' '$2=="root"' "$tmp" | wc -l | tr -d ' ')" -eq 1 ] || {
  rm -f "$tmp"
  die "need exactly one root key"
}
awk -F'\t' '{print $3}' "$tmp" | sort | uniq -d | grep -q . && {
  rm -f "$tmp"
  die "labels must be unique"
}
mv "$tmp" "$YKHK_STATE/devices.tsv"
cat "$YKHK_STATE/devices.tsv"
