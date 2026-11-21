#!/bin/sh
# B4a: export, bundle under an independent passphrase, stage in RAM, copy to Persistent.
# Then run b4-copy.sh backup and b4-copy.sh public, one stick at a time (one USB-C port).
# Needs the subkeys (B3). Expects YKHK_SUBKEYS subkeys (default 6).
. "$(dirname "$0")/lib.sh"
use_gnupghome
need_fpr
PERSIST=${YKHK_PERSIST_DIR:-$HOME/Persistent}
b4_gate
[ -d "$PERSIST" ] && [ -w "$PERSIST" ] || die "$PERSIST is missing or not writable. Unlock the Persistent Storage."
say "Backup passphrase: independent of the primary passphrase, every PIN and every LUKS passphrase."
confirm "Ready to export and encrypt?" || die "stopped"
stage="$YKHK_STATE/stage"
rm -rf "$stage" # a rerun must not mix files from an earlier run
mkdir -p "$stage"
chmod 700 "$stage"
w=$(mktemp -d)
chmod 700 "$w"
trap 'rm -rf "$w"' EXIT
b4_bundle "$w"
mv "$w/identity-backup.tar.gpg" "$w/public.asc" "$stage/"
b4_record "$stage/ceremony-record.txt"
rm -rf "$w" # plaintext secret export gone; only the encrypted bundle remains
{ cp "$stage/identity-backup.tar.gpg" "$PERSIST/" && cmp -s "$stage/identity-backup.tar.gpg" "$PERSIST/identity-backup.tar.gpg"; } ||
  die "copy to Persistent failed"
sync
say "Staged in RAM and copied to $PERSIST. Next: b4-copy.sh backup, then b4-copy.sh public."
mark_done B4a
