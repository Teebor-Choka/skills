#!/bin/sh
# Read-only check of the preconditions for the next step: the device plan and the step markers.
# Run it after every step. It prints PASS or FAIL lines and exits 1 on any FAIL. It never prompts and never
# changes the plan, the markers, a key or a stick. For a plugged-in key, use c-check.sh.
. "$(dirname "$0")/lib.sh"
fail=0
ok() { say "PASS $1"; }
bad() {
  say "FAIL $1"
  fail=1
}
[ -s "$YKHK_STATE/devices.tsv" ] || {
  say "FAIL no device plan. Run init-plan.sh COUNT."
  exit 1
}
plan="$YKHK_STATE/devices.tsv"
roots=$(awk -F'\t' '$2=="root"' "$plan" | wc -l | tr -d ' ')
if [ "$roots" -eq 1 ]; then ok "exactly one root key"; else bad "the plan has $roots root keys, expected 1"; fi
badroles=$(awk -F'\t' '$2!="root" && $2!="daily" {print $3}' "$plan")
if [ -z "$badroles" ]; then ok "every role is root or daily"; else bad "invalid role for: $badroles"; fi
badlabels=$(awk -F'\t' '$3 !~ /^[a-z0-9-]+$/ {print $3}' "$plan")
if [ -z "$badlabels" ]; then ok "every label uses [a-z0-9-]"; else bad "invalid label: $badlabels"; fi
dups=$(awk -F'\t' '{print $3}' "$plan" | sort | uniq -d)
if [ -z "$dups" ]; then ok "labels are unique"; else bad "duplicate labels: $dups"; fi
unverified=$(unverified_labels | tr '\n' ' ')
if [ -z "$unverified" ]; then ok "every key is confirmed genuine"; else bad "keys not confirmed genuine (phase A): $unverified"; fi
if [ -f "$YKHK_STATE/done.A1" ] && [ -n "$unverified" ]; then bad "A1 is marked done but not verified: $unverified"; fi
missing=''
for m in $(steps_all | cut -d'|' -f3); do
  if [ -f "$YKHK_STATE/done.$m" ]; then
    [ -z "$missing" ] || bad "step $m is marked done but $missing is not"
  elif [ -z "$missing" ]; then
    missing=$m
  fi
done
if [ -n "$missing" ]; then ok "next ceremony step: $missing"; else ok "all ceremony steps done"; fi
[ "$fail" -eq 0 ] || exit 1
