#!/bin/sh
# Test files run check strings through eval, pass word lists unquoted on purpose, and call helpers
# from those strings, so these checks do not apply: SC2016 single-quoted eval strings, SC2086 unquoted
# word lists, SC2329 helpers used by eval, SC2269 exported passthrough, SC2059 printf with an answer
# string, SC2034 captured output read through eval.
# shellcheck disable=SC2016,SC2086,SC2329,SC2269,SC2059,SC2034
# Rehearse B0, B2, B4, B5 with a software keyring in temp dirs. No YubiKey, no secrets.
# Needs gpg. Uses a stub ykman. Run: sh tests/rehearse-ceremony.sh
D=$(cd "$(dirname "$0")/../scripts" && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/ykhk-test.XXXXXX")
# pty SCRIPT: run sh SCRIPT under a pseudo-terminal. util-linux script takes the command with -c, BSD script as words.
pty() { if script -V 2>/dev/null | grep -q util-linux; then script -q -e -c "sh '$1'" /dev/null; else script -q /dev/null sh "$1"; fi; }
cd "$T" || exit 1
mkdir -p bk pub per bin st
printf '#!/bin/sh\necho "ykman stub"\n' >bin/ykman
chmod +x bin/ykman
PATH=$T/bin:$PATH
YKHK_STATE=$T/st
YKHK_BACKUP_DIR=$T/bk
YKHK_PUBLIC_DIR=$T/pub
YKHK_PERSIST_DIR=$T/per
YKHK_GPG_EXTRA='--batch --pinentry-mode loopback --passphrase tp'
export PATH YKHK_STATE YKHK_BACKUP_DIR YKHK_PUBLIC_DIR YKHK_PERSIST_DIR YKHK_GPG_EXTRA
printf '1\troot\troot\t1\t5.7.4\tyes\n' >st/devices.tsv
fail=0
check() { if eval "$2"; then echo "PASS $1"; else
  echo "FAIL $1"
  fail=1
fi; }
printf 'y\ny\ny\ny\ny\ny\ny\ny\n' >yes.txt # enough answers for any one script

YKHK_TTY=$T/yes.txt sh "$D/b0-start.sh" >/dev/null 2>&1
check "b0 creates keyring" '[ -s st/gnupghome ] && [ -f st/done.B0 ]'
YKHK_TTY=$T/yes.txt sh "$D/b2-primary.sh" "Test User <t@example.org>" >/dev/null 2>&1
check "b2 writes 40-char fingerprint" '[ "$(wc -c < st/primary.fpr | tr -d " ")" -eq 41 ]'
YKHK_TTY=$T/yes.txt sh "$D/b2-primary.sh" "Test User <t@example.org>" >/dev/null 2>&1
check "b2 refuses a second primary key" '[ $? -ne 0 ] && [ "$(wc -l < st/primary.fpr | tr -d " ")" -eq 1 ]'

GH=$(cat st/gnupghome)
F=$(cat st/primary.fpr)
for spec in "ed25519 sign" "cv25519 encr" "ed25519 auth" "ed25519 sign" "cv25519 encr" "ed25519 auth"; do
  GNUPGHOME=$GH gpg $YKHK_GPG_EXTRA --quick-add-key "$F" $spec 1y >/dev/null 2>&1
done
YKHK_SUBKEYS=7 YKHK_TTY=$T/yes.txt sh "$D/b4-backup.sh" >/dev/null 2>&1
check "b4 refuses a wrong subkey count" '[ $? -ne 0 ] && [ ! -f st/done.B4a ]'
sh "$D/b4-copy.sh" backup >/dev/null 2>&1
check "b4-copy refuses before the export" '[ $? -ne 0 ] && [ ! -e bk/identity-backup.tar.gpg ]'
# b4 asks four gen-revoke questions on a real tty: give it a pty (script) and delayed answers.
(
  sleep 6
  printf 'y\n'
  sleep 1
  printf '0\n'
  sleep 1
  printf '\n'
  sleep 1
  printf 'y\n'
  sleep 4
) |
  YKHK_GPG_EXTRA='--pinentry-mode loopback --passphrase tp' YKHK_TTY=$T/yes.txt \
    pty "$D/b4-backup.sh" >b4.log 2>&1
check "b4 stages and copies to Persistent" '[ -s per/identity-backup.tar.gpg ] && [ -f st/done.B4a ] && [ ! -f st/done.B4 ]'
sh "$D/b4-copy.sh" backup >/dev/null 2>&1
check "b4-copy backup writes the bundle only" '[ -s bk/identity-backup.tar.gpg ] && [ ! -e pub/public.asc ] && [ ! -f st/done.B4 ]'
sh "$D/b4-copy.sh" public >/dev/null 2>&1
check "b4-copy public writes key and record; B4 done" '[ -s pub/public.asc ] && grep -q "^primary: $F" pub/ceremony-record.txt && [ -f st/done.B4 ]'
check "b4 leaves no plaintext secret on the sticks" '! grep -rl "BEGIN PGP PRIVATE KEY" bk per pub'
check "record lists six subkeys" '[ "$(grep -c "^subkey(" pub/ceremony-record.txt)" -eq 6 ]'
sh "$D/b5-verify-backup.sh" >/dev/null 2>&1
check "b5 passes on good backups" '[ -f st/done.B5 ]'

rm -f st/done.B5
printf 'X' | dd of=per/identity-backup.tar.gpg bs=1 seek=200 conv=notrunc 2>/dev/null # flip a byte mid-file
sh "$D/b5-verify-backup.sh" >/dev/null 2>&1
check "b5 fails on a corrupted backup" '[ $? -ne 0 ] && [ ! -f st/done.B5 ]'

# One-shot variant (hub setups): reset the outputs and run it under a pty with delayed answers.
rm -rf bk/* pub/* per/* st/stage
rm -f st/done.B4* st/done.B5
(
  sleep 6
  printf 'y\n'
  sleep 1
  printf '0\n'
  sleep 1
  printf '\n'
  sleep 1
  printf 'y\n'
  sleep 4
) |
  YKHK_GPG_EXTRA='--pinentry-mode loopback --passphrase tp' YKHK_TTY=$T/yes.txt \
    pty "$D/b4-backup-all.sh" >b4all.log 2>&1
check "b4-backup-all writes all three destinations" '[ -s bk/identity-backup.tar.gpg ] && [ -s per/identity-backup.tar.gpg ] && [ -s pub/public.asc ] && [ -s pub/ceremony-record.txt ] && [ -f st/done.B4 ]'
sh "$D/b5-verify-backup.sh" >/dev/null 2>&1
check "b5 passes on the one-shot backups" '[ -f st/done.B5 ]'

GNUPGHOME=$GH gpgconf --kill all 2>/dev/null
rm -rf "$T"
exit $fail
