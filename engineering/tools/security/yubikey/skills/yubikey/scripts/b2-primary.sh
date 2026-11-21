#!/bin/sh
# B2: generate the certify-only primary key in the RAM keyring. Usage: b2-primary.sh "Name <email>"
. "$(dirname "$0")/lib.sh"
use_gnupghome
[ ! -s "$YKHK_STATE/primary.fpr" ] || die "a primary key exists ($(cat "$YKHK_STATE/primary.fpr")). Do not create a second one."
uid=${1-}
if [ -z "$uid" ]; then
  ask "Identity (Name <email>)?" "${YKHK_IDENTITY-}"
  uid=$REPLY
fi
case $uid in *'<'*'@'*'>') ;; *) die 'usage: b2-primary.sh "Name <email>"' ;; esac
say "Identity: $uid"
confirm "Create the primary key (ed25519, certify only, no expiry) for this identity?" || die "stopped"
say "A passphrase prompt follows. Use a strong passphrase and store it in your password manager."
g --quick-generate-key "$uid" ed25519 cert never || die "key generation failed"
fpr=$(g --batch --with-colons --list-secret-keys | awk -F: '/^fpr:/ {print $10; exit}')
[ "${#fpr}" -eq 40 ] || die "could not read a 40-character fingerprint"
printf '%s\n' "$fpr" >"$YKHK_STATE/primary.fpr"
say "Primary fingerprint: $(printf '%s' "$fpr" | sed 's/\(....\)/\1 /g')"
printf '%s\n' "$uid" >"$YKHK_STATE/identity"
mark_done B2
confirm "Did you record it on paper or a second device?" || say "Record it before B4. It is saved in $YKHK_STATE/primary.fpr."
