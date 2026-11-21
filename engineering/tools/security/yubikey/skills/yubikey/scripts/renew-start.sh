#!/bin/sh
# Renewal session on Tails (offline), the step before subkey-expiry.sh: a RAM keyring holding the public identity from
# stick 3, and the primary fingerprint in the state. Usage: renew-start.sh PRIMARY_FPR [DIR [PUBKEY_DIGEST]]
# PRIMARY_FPR is the fingerprint you wrote down in B2. DIR defaults to /media/amnesia/PUBLIC. The key on the stick must
# be exactly one primary key with exactly that fingerprint. Afterwards plug in the ROOT card and run gpg --card-status
# once, so gpg learns that the primary key is on the card. PUBKEY_DIGEST is the digest of public.asc from your paper
# (written by b9 or after your last export): it catches a stale copy, which the fingerprint cannot.
. "$(dirname "$0")/lib.sh"
expected=$(printf '%s' "${1-}" | tr -d ' ' | tr '[:lower:]' '[:upper:]')
printf '%s' "$expected" | grep -Eq '^[0-9A-F]{40}$' || die "usage: renew-start.sh PRIMARY_FPR [DIR]. PRIMARY_FPR is the 40-hex fingerprint from your paper record."
dir=${2:-/media/amnesia/PUBLIC}
[ -s "$dir/public.asc" ] || die "public.asc missing in $dir"
check_pubkey_digest "$dir/public.asc" "${3-}"
sh "$(dirname "$0")/b0-start.sh" || exit 1
use_gnupghome
g --batch --quiet --import "$dir/public.asc" 2>/dev/null || die "could not import public.asc"
keys=$(g --batch --with-colons --list-keys)
npub=$(printf '%s\n' "$keys" | grep -c '^pub:')
first=$(printf '%s\n' "$keys" | awk -F: '/^fpr:/ {print $10; exit}')
{ [ "$npub" -eq 1 ] && [ "$first" = "$expected" ]; } || die "public.asc must hold exactly one primary key and it must be $expected. Do not continue."
printf '%s\n' "$expected" >"$YKHK_STATE/primary.fpr"
say "RAM keyring ready for $expected. Plug in the ROOT card, run gpg --card-status once, then subkey-expiry.sh PERIOD FPR..."
