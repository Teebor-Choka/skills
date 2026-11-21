#!/bin/sh
# B4, one shot: export, bundle under an independent passphrase, copy to BACKUP, Persistent and PUBLIC.
# Use only when all three destinations are mounted at once (a hub). With one free port, use
# b4-backup.sh then b4-copy.sh backup and b4-copy.sh public instead.
# Needs the subkeys (B3). Expects YKHK_SUBKEYS subkeys (default 6).
. "$(dirname "$0")/lib.sh"
use_gnupghome
need_fpr
BACKUP=${YKHK_BACKUP_DIR:-/media/amnesia/BACKUP}
PUBLIC=${YKHK_PUBLIC_DIR:-/media/amnesia/PUBLIC}
PERSIST=${YKHK_PERSIST_DIR:-$HOME/Persistent}
b4_gate
for dir in "$BACKUP" "$PUBLIC" "$PERSIST"; do
  [ -d "$dir" ] && [ -w "$dir" ] || die "$dir is missing or not writable. Unlock and mount it."
done
say "Backup passphrase: independent of the primary passphrase, every PIN and every LUKS passphrase."
confirm "Ready to export and encrypt?" || die "stopped"
w=$(mktemp -d)
chmod 700 "$w"
trap 'rm -rf "$w"' EXIT
b4_bundle "$w"
{ cp "$w/identity-backup.tar.gpg" "$BACKUP/" && cp "$w/identity-backup.tar.gpg" "$PERSIST/"; } || die "copy failed"
cp "$w/public.asc" "$PUBLIC/"
b4_record "$PUBLIC/ceremony-record.txt"
sync
say "Copied: $BACKUP/identity-backup.tar.gpg, $PERSIST/identity-backup.tar.gpg, $PUBLIC/public.asc, $PUBLIC/ceremony-record.txt"
mark_done B4a
mark_done B4.backup
mark_done B4.public
mark_done B4
