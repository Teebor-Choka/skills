#!/bin/sh
# Set or list subkey expiry in the ceremony keyring. Needs the primary key (RAM keyring or root card).
#   subkey-expiry.sh                 list subkeys with their expiry
#   subkey-expiry.sh PERIOD FPR...   set PERIOD (1y, 18m, 90d, a date) on the named subkeys
. "$(dirname "$0")/lib.sh"
use_gnupghome
need_fpr
if [ $# -eq 0 ]; then
  g --list-secret-keys --with-subkey-fingerprints "$KEYFPR" # a subkey with no [expires: ...] never expires
  exit 0
fi
period=$1
shift
valid_period "$period" || die "bad period: $period (use 1y, 18m, 90d or a date; zero and never are not allowed)"
[ $# -gt 0 ] || die "name at least one subkey fingerprint"
tbl=$(subkey_table) # one keyring scan; the primary key is not in this table
for f in "$@"; do
  printf '%s\n' "$tbl" | awk -v f="$f" '$1==f {ok=1} END {exit !ok}' || die "$f is not a subkey of $KEYFPR"
done
say "Primary passphrase window follows."
g --quick-set-expire "$KEYFPR" "$period" "$@" || die "setting the expiry failed"
left=$(subkeys_without_expiry)
[ "$left" -eq 0 ] || die "$left subkeys are still without expiry. Set one on each before you go on."
say "Every subkey now has an expiry."
