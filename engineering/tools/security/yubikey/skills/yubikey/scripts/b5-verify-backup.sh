#!/bin/sh
# B5 (blocking): restore each bundle into a fresh RAM keyring and certify a throwaway key with it.
# keytocard (B6) must not run until this passes.
. "$(dirname "$0")/lib.sh"
use_gnupghome
need_fpr
need_done B4
BACKUP=${YKHK_BACKUP_DIR:-/media/amnesia/BACKUP}
PERSIST=${YKHK_PERSIST_DIR:-$HOME/Persistent}

verify_one() {
  bundle=$1
  [ -f "$bundle" ] || {
    say "missing: $bundle"
    return 1
  }
  ch=$(mktemp -d)
  xd=$(mktemp -d)
  th=$(mktemp -d)
  chmod 700 "$ch" "$th"
  rc=1
  say "Decrypting $bundle (enter the backup passphrase)"
  if g --decrypt --output "$xd/bundle.tar" "$bundle" && tar -x -C "$xd" -f "$xd/bundle.tar" &&
    [ -s "$xd/primary-secret.asc" ] && [ -s "$xd/revoke.asc" ] &&
    gh "$ch" --import "$xd/primary-secret.asc" 2>/dev/null &&
    [ "$(fprs "$GNUPGHOME")" = "$(fprs "$ch")" ] &&
    gh "$th" --batch --pinentry-mode loopback --passphrase '' \
      --quick-generate-key "Backup Test <backup-test@invalid>" ed25519 cert 1d 2>/dev/null; then
    tfpr=$(gh "$th" --with-colons --list-keys backup-test@invalid | awk -F: '/^fpr:/ {print $10; exit}')
    gh "$th" --export "$tfpr" >"$xd/target.asc"
    say "Certifying a test key (enter the primary passphrase)"
    gh "$ch" --import "$xd/target.asc" 2>/dev/null &&
      gh "$ch" --local-user "$KEYFPR!" --quick-sign-key "$tfpr" 2>/dev/null && rc=0
  fi
  for h in "$ch" "$th"; do (
    GNUPGHOME=$h
    export GNUPGHOME
    gpgconf --kill all 2>/dev/null
  ); done
  rm -rf "$ch" "$xd" "$th"
  return $rc
}

fail=0
for b in "$BACKUP/identity-backup.tar.gpg" "$PERSIST/identity-backup.tar.gpg"; do
  if verify_one "$b"; then say "OK: $b"; else
    say "FAILED: $b"
    fail=1
  fi
done
[ "$fail" -eq 0 ] || die "restore test failed. Do NOT run keytocard. Fix or redo B4."
say "Both backups restore, with all fingerprints matching."
mark_done B5
