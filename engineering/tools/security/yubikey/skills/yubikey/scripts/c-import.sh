#!/bin/sh
# Mac side: import the public identity from the PUBLIC stick after the ceremony.
# Usage: c-import.sh EXPECTED_FPR [DIR [PUBKEY_DIGEST]]   (DIR defaults to /Volumes/PUBLIC)
# EXPECTED_FPR is the primary fingerprint the user wrote down in B2, typed or read from that paper or second
# device. Never copy it from the stick: the record and public.asc sit on the same writable stick, so comparing
# them with each other proves they agree, not that they are yours. Spaces and case in EXPECTED_FPR are ignored.
# The key is checked in a throwaway keyring, and the checked copy is the one imported.
. "$(dirname "$0")/lib.sh"
expected=$(printf '%s' "${1-}" | tr -d ' ' | tr '[:lower:]' '[:upper:]')
case $expected in
[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]) ;;
*) die "usage: c-import.sh EXPECTED_FPR [DIR]. EXPECTED_FPR is the 40-hex primary fingerprint from your paper record." ;;
esac
dir=${2:-/Volumes/PUBLIC}
rec="$dir/ceremony-record.txt"
[ -s "$rec" ] && [ -s "$dir/public.asc" ] || die "ceremony-record.txt or public.asc missing in $dir"
T=$(mktemp -d)
chmod 700 "$T"
trap 'rm -rf "$T"' EXIT
cp "$dir/public.asc" "$T/public.asc"        # one read of the stick: the bytes checked below are the bytes imported
check_pubkey_digest "$T/public.asc" "${3-}" # PUBKEY_DIGEST: the digest from your paper; it catches a stale copy
primary=$(awk '/^primary:/ {print $2}' "$rec")
[ "$primary" = "$expected" ] || die "the record names $primary, not the fingerprint you gave. Do not import. Check the stick and your paper record."
mkdir -m 700 "$T/h"
GNUPGHOME=$T/h gpg --batch --quiet --import "$T/public.asc" 2>/dev/null || die "could not read public.asc"
keys=$(GNUPGHOME=$T/h gpg --with-colons --list-keys --with-subkey-fingerprints 2>/dev/null)
npub=$(printf '%s\n' "$keys" | grep -c '^pub:')
nsub=$(printf '%s\n' "$keys" | grep -c '^sub:')
[ "$npub" -eq 1 ] || die "public.asc holds $npub primary keys, expected exactly 1. Do not import."
[ "$nsub" -eq "${YKHK_SUBKEYS:-6}" ] || die "public.asc holds $nsub subkeys, expected ${YKHK_SUBKEYS:-6}. Do not import."
got=$(printf '%s\n' "$keys" | awk -F: '/^fpr:/ {print $10}' | sort)
want=$({
  echo "$expected"
  awk '/^subkey\(/ {print $2}' "$rec"
} | sort)
[ "$got" = "$want" ] || die "the key on the stick does not match your fingerprint and the record. Do not import it."
none=$(printf '%s\n' "$keys" | awk -F: '/^sub:/ && $7=="" {n++} END {print n+0}')
[ "$none" -eq 0 ] || say "WARNING: $none subkeys have no expiry. Fix with subkey-expiry.sh in a new ceremony."
gpg --batch --import "$T/public.asc" 2>&1 | tail -2
printf '%s:6:\n' "$expected" | gpg --import-ownertrust 2>&1 | tail -1
say "Imported $expected with $nsub subkeys. It matches your fingerprint and the record."
