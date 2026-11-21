#!/bin/sh
# Ceremony driver, run on Tails: shows the next step, asks, runs it, repeats until B9 is done.
# The only command to type: sh ~/scripts/go.sh   (state: YKHK_STATE, in RAM on Tails)
. "$(dirname "$0")/lib.sh"
D=$(cd "$(dirname "$0")" && pwd)
need_init
while :; do
  next=$(next_step)
  [ -n "$next" ] || {
    say ""
    ceremony_bar
    say "Ceremony complete. Shut Tails down and store the root key, stick 1 and stick 2 apart."
    exit 0
  }
  cmd=${next%%|*}
  rest=${next#*|}
  desc=${rest%%|*}
  say ""
  ceremony_bar
  say "Next: $desc   ($cmd)"
  confirm "Run it now?" || {
    say "Paused. Run go.sh again to continue."
    exit 0
  }
  # shellcheck disable=SC2086
  sh "$D/${cmd%% *}" ${cmd#"${cmd%% *}"} || die "step failed: $cmd. Read the message, then run go.sh again."
  mark=${rest##*|}
  sh "$D/assert-card.sh" "$mark" || die "card state does not match after $mark. Fix the card, check it with: sh $D/assert-card.sh $mark"
done
