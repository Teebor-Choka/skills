#!/bin/sh
# Test files run check strings through eval, pass word lists unquoted on purpose, and call helpers
# from those strings, so these checks do not apply: SC2016 single-quoted eval strings, SC2086 unquoted
# word lists, SC2329 helpers used by eval, SC2269 exported passthrough, SC2059 printf with an answer
# string, SC2034 captured output read through eval.
# shellcheck disable=SC2016,SC2086,SC2329,SC2269,SC2059,SC2034
# Rehearse the step scripts (go.sh order, card gating, B1, B7, B8, expiry gate, usb-prepare, c-check)
# with a stub ykman and ssh-keygen and a software keyring. No YubiKey, no secrets. Run: sh tests/rehearse-steps.sh
D=$(cd "$(dirname "$0")/../scripts" && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/ykhk-steps.XXXXXX")
cd "$T" || exit 1
mkdir -p bin st home stick
STUB=$T/stub
mkdir -p "$STUB"
cat >bin/ykman <<'STUBEOF'
#!/bin/sh
echo "ykman $*" >> "$STUB/calls"
case "$1 $2" in
  "list --serials") cat "$STUB/serial" ;;
  "openpgp info") cat "$STUB/pgpinfo" ;;
  "info ") printf "Firmware version: 5.7.4\n" ;;
  "fido info") cat "$STUB/fidoinfo" ;;
  "openpgp keys") [ "$3" = set-touch ] && [ "$4" = --help ] && echo "  -a, --admin-pin TEXT" ;;
esac
exit 0
STUBEOF
cat >bin/ssh-keygen <<'STUBEOF'
#!/bin/sh
f=; mode=gen
while [ $# -gt 0 ]; do case $1 in -f) f=$2; shift ;; -l) mode=list ;; esac; shift; done
if [ $mode = list ]; then echo "256 SHA256:TESTFP stub (ED25519-SK)"; else echo handle > "$f"; echo "sk-ssh-ed25519@openssh.com AAAA stub" > "$f.pub"; fi
STUBEOF
printf '#!/bin/sh\nexit 0\n' >bin/open # the wrapper opens the Yubico page: never open a browser in a test
chmod +x bin/*
# The real ssh-keygen, alone in its own dir: the SSH key-type checks below need it ahead of the stub, and nothing else.
mkdir realbin
ln -s "$(command -v ssh-keygen)" realbin/ssh-keygen
PATH=$T/bin:$PATH
HOME=$T/home
YKHK_STATE=$T/st
STUB=$STUB
YKHK_GPG_EXTRA='--batch --pinentry-mode loopback --passphrase tp'
export PATH HOME YKHK_STATE STUB YKHK_GPG_EXTRA
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n3\tdaily\tnfc\t333\t5.7.4\tyes\n' >st/devices.tsv
fail=0
check() { if eval "$2"; then echo "PASS $1"; else
  echo "FAIL $1"
  fail=1
fi; }
ans() {
  printf "$1" >"$T/ans"
  YKHK_TTY=$T/ans
  export YKHK_TTY
}
reset() { rm -f st/done.* "$STUB/calls"; }

# 1. step order
nxt() { sh -c ". $D/lib.sh; next_step" | cut -d'|' -f1; }
check "first step is b0" '[ "$(nxt)" = "b0-start.sh" ]'
touch st/done.B0
check "then B1 for root" '[ "$(nxt)" = "b1-pins.sh root" ]'
touch st/done.B1.root st/done.B1.nano st/done.B1.nfc
check "then B2" '[ "$(nxt)" = "b2-primary.sh" ]'
touch st/done.B2
check "then B3 nano" '[ "$(nxt)" = "b3-subkeys.sh nano" ]'
touch st/done.B3.nano st/done.B3.nfc st/done.B4a st/done.B4.backup st/done.B4.public st/done.B5
check "B5 before B6" '[ "$(nxt)" = "b6-keytocard.sh" ]'
touch st/done.B6 st/done.B7.root st/done.B7.nano st/done.B7.nfc st/done.B8.nano st/done.B8.nfc
check "B9 last" '[ "$(nxt)" = "b9-end.sh" ]'
touch st/done.B9
check "nothing after B9" '[ -z "$(nxt)" ]'
reset

# 2. go.sh pauses on n, and reports completion
ans 'n\n'
out=$(sh "$D/go.sh" 2>&1)
check "go.sh pauses when you say no" 'echo "$out" | grep -q Paused'
touch st/done.B0 st/done.B1.root st/done.B1.nano st/done.B1.nfc st/done.B2 st/done.B3.nano st/done.B3.nfc st/done.B4a st/done.B4.backup st/done.B4.public st/done.B5 st/done.B6 st/done.B7.root st/done.B7.nano st/done.B7.nfc st/done.B8.nano st/done.B8.nfc st/done.B9
ans ''
out=$(sh "$D/go.sh" 2>&1)
check "go.sh reports completion" 'echo "$out" | grep -q "Ceremony complete"'
reset

# 3. card gating
echo 999 >"$STUB/serial"
ans '\nn\n'
sh "$D/b1-pins.sh" nano >/dev/null 2>&1
check "b1 refuses the wrong key" '[ $? -ne 0 ] && [ ! -f st/done.B1.nano ]'
echo 222 >"$STUB/serial"
ans '\ny\ny\n'
sh "$D/b1-pins.sh" nano >/dev/null 2>&1
check "b1 sets all PINs on a daily key" 'grep -q "change-pin" "$STUB/calls" && grep -q "change-admin-pin" "$STUB/calls" && grep -q "change-reset-code" "$STUB/calls" && grep -q "fido access change-pin" "$STUB/calls" && grep -q "otp delete 1" "$STUB/calls" && [ -f st/done.B1.nano ]'
rm -f "$STUB/calls"
echo 111 >"$STUB/serial"
ans '\ny\n'
sh "$D/b1-pins.sh" root >/dev/null 2>&1
check "b1 on root skips FIDO2 and OTP" '! grep -q fido "$STUB/calls" && ! grep -q otp "$STUB/calls" && [ -f st/done.B1.root ]'
reset

# 4. B7 read-back
daily_ok='Require PIN for signature:  Once
Signature key:
  Touch policy: Cached
Decryption key:
  Touch policy: Off
Authentication key:
  Touch policy: Off'
echo 222 >"$STUB/serial"
printf '%s\n' "$daily_ok" >"$STUB/pgpinfo"
ans '\npin\n'
sh "$D/b7-touch.sh" nano >/dev/null 2>&1
check "b7 passes on a correct daily key" '[ -f st/done.B7.nano ] && grep -q "set-signature-policy once" "$STUB/calls" && grep -q -e "-a pin" "$STUB/calls"'
rm -f st/done.B7.nano
printf '%s\n' "$daily_ok" | sed 's/Once/Always/' >"$STUB/pgpinfo"
ans '\npin\n'
sh "$D/b7-touch.sh" nano >/dev/null 2>&1
check "b7 fails when the signature PIN is still Always" '[ $? -ne 0 ] && [ ! -f st/done.B7.nano ]'
echo 111 >"$STUB/serial"
printf 'Signature key:\n  Touch policy: On\nDecryption key:\n  Touch policy: Off\nAuthentication key:\n  Touch policy: Off\n' >"$STUB/pgpinfo"
ans '\npin\n'
sh "$D/b7-touch.sh" root >/dev/null 2>&1
check "b7 passes on root with touch On" '[ -f st/done.B7.root ]'
rm -f st/done.B7.root
printf 'Signature key:\n  Touch policy: Cached\n' >"$STUB/pgpinfo"
ans '\npin\n'
sh "$D/b7-touch.sh" root >/dev/null 2>&1
check "b7 fails on root with touch Cached" '[ $? -ne 0 ] && [ ! -f st/done.B7.root ]'
reset

# 5. B8
echo 222 >"$STUB/serial"
ans '\n'
sh "$D/b8-ssh.sh" nano >/dev/null 2>&1
check "b8 refuses without an identity" '[ ! -f st/done.B8.nano ]'
echo "Test <t@example.org>" >st/identity
ans '\n'
sh "$D/b8-ssh.sh" nano >b8.out 2>&1
check "b8 tells the user to write the fingerprint on paper" 'grep -q "on paper" b8.out'
check "b8 keeps handle and pub in the state dir" '[ -s st/ssh/id_ed25519_sk_nano ] && [ -s st/ssh/id_ed25519_sk_nano.pub ] && [ -f st/done.B8.nano ]'
ans '\n'
sh "$D/b8-ssh.sh" nano >/dev/null 2>&1
check "b8 will not overwrite a handle" '[ $? -ne 0 ]'
reset

# 6. expiry gate and subkey-expiry (software keyring)
GH=$T/gh
mkdir -m 700 "$GH"
export GNUPGHOME=$GH
gpg $YKHK_GPG_EXTRA --quick-generate-key "R <r@example.org>" ed25519 cert never >/dev/null 2>&1
F=$(gpg --with-colons -K | awk -F: '/^fpr:/ {print $10; exit}')
echo "$GH" >st/gnupghome
echo "$F" >st/primary.fpr
for e in 1y 1y 1y never never never; do gpg $YKHK_GPG_EXTRA --quick-add-key "$F" ed25519 sign $e >/dev/null 2>&1; done
cnt() { sh -c ". $D/lib.sh; use_gnupghome; need_fpr; subkeys_without_expiry"; }
check "gate counts 3 subkeys without expiry" '[ "$(cnt)" = 3 ]'
mkdir -p pdir bdir ydir
ans 'y\n'
YKHK_PERSIST_DIR=$T/pdir YKHK_BACKUP_DIR=$T/bdir YKHK_PUBLIC_DIR=$T/ydir YKHK_SUBKEYS=6 sh "$D/b4-backup.sh" >b4.out 2>&1
check "b4 refuses subkeys without expiry" 'grep -q "no expiry" b4.out && [ ! -f st/done.B4a ]'
NOEXP=$(gpg --with-colons -K --with-subkey-fingerprints | awk -F: '/^ssb:/ {e=$7} /^fpr:/ && n>0 {if (e=="") print $10} /^ssb:/ {n=1}')
check "subkey-expiry rejects never" '! sh "$D/subkey-expiry.sh" never $NOEXP >/dev/null 2>&1'
check "subkey-expiry rejects a non-subkey" '! sh "$D/subkey-expiry.sh" 1y 0000000000000000000000000000000000000000 >/dev/null 2>&1'
check "subkey-expiry rejects the primary key by name" 'sh "$D/subkey-expiry.sh" 1y "$F" 2>&1 | grep -q "is not a subkey"'
two=$(printf '%s\n' $NOEXP | sed -n '1,2p')
sh "$D/subkey-expiry.sh" 1y $two >se.out 2>&1
check "subkey-expiry fails while a subkey is still without expiry" '[ $? -ne 0 ] && grep -q "still without expiry" se.out'
vp() { sh -c ". $D/lib.sh; valid_period \"\$1\"" _ "$1" >/dev/null 2>&1; }
check "valid_period accepts 1y, 18m, 90d, 2w and a date" 'vp 1y && vp 18m && vp 90d && vp 2w && vp 2027-11-15'
check "valid_period refuses zero, never and junk" '! vp 0 && ! vp 0d && ! vp 0y && ! vp 00d && ! vp never && ! vp 1x2y && ! vp "1y --x"'
sh "$D/subkey-expiry.sh" 1y $NOEXP >/dev/null 2>&1
check "subkey-expiry sets the date, gate reads 0" '[ "$(cnt)" = 0 ]'
# c-import: the typed fingerprint is the anchor, not the stick
mkdir -p ci_stick
gpg --armor --export "$F" >ci_stick/public.asc
{
  echo "primary: $F"
  gpg --with-colons --list-secret-keys --with-subkey-fingerprints "$F" | awk -F: '/^ssb:/ {use=$12} /^fpr:/ && use {print "subkey(" use "): " $10; use=""}'
} >ci_stick/ceremony-record.txt
mkdir -m 700 mac1 mac2 mac3
lower=$(printf '%s' "$F" | tr 'A-F' 'a-f')
spaced=$(printf '%s' "$lower" | sed 's/\(....\)/\1 /g')
GNUPGHOME=$T/mac1 sh "$D/c-import.sh" "$spaced" ci_stick >ci.out 2>&1
check "c-import accepts the typed fingerprint (spaces and case ignored)" '[ $? -eq 0 ] && GNUPGHOME=$T/mac1 gpg --export-ownertrust 2>/dev/null | grep -q "^$F:6:"'
check "c-import reports counted subkeys" 'grep -q "with 6 subkeys" ci.out'
other=$(printf '%040d' 7 | tr '0' 'A')
GNUPGHOME=$T/mac2 sh "$D/c-import.sh" "$other" ci_stick >ci.out 2>&1
check "c-import refuses a fingerprint that is not the record's" '[ $? -ne 0 ] && grep -q "Do not import" ci.out && ! GNUPGHOME=$T/mac2 gpg --list-keys 2>/dev/null | grep -q pub'
# a forger puts a second key in public.asc and names it in the record; the typed fingerprint is the real one
GA=$T/gatk
mkdir -m 700 "$GA"
GNUPGHOME=$GA gpg $YKHK_GPG_EXTRA --quick-generate-key "A <a@example.org>" ed25519 cert never >/dev/null 2>&1
FA=$(GNUPGHOME=$GA gpg --with-colons -K | awk -F: '/^fpr:/ {print $10; exit}')
mkdir -p ci_forged
{
  gpg --armor --export "$F"
  GNUPGHOME=$GA gpg --armor --export "$FA"
} >ci_forged/public.asc
{
  echo "primary: $FA"
  grep '^subkey(' ci_stick/ceremony-record.txt
} >ci_forged/ceremony-record.txt
GNUPGHOME=$T/mac3 sh "$D/c-import.sh" "$F" ci_forged >ci.out 2>&1
check "c-import refuses a forged record that names another primary" '[ $? -ne 0 ] && ! GNUPGHOME=$T/mac3 gpg --list-keys 2>/dev/null | grep -q pub'
{
  echo "primary: $F"
  grep '^subkey(' ci_stick/ceremony-record.txt
} >ci_forged/ceremony-record.txt
GNUPGHOME=$T/mac3 sh "$D/c-import.sh" "$F" ci_forged >ci.out 2>&1
check "c-import refuses an asc with an extra primary key" '[ $? -ne 0 ] && grep -q "primary keys" ci.out && ! GNUPGHOME=$T/mac3 gpg --list-keys 2>/dev/null | grep -q pub'
for h in "$GA" "$T/mac1" "$T/mac2" "$T/mac3"; do GNUPGHOME=$h gpgconf --kill all 2>/dev/null; done
# public.asc digest: a stale genuine copy has the same fingerprints, only an off-stick digest detects it
dg=$(sh -c ". $D/lib.sh; sha ci_stick/public.asc" | cut -d' ' -f1)
mkdir -m 700 mac4
GNUPGHOME=$T/mac4 sh "$D/c-import.sh" "$F" ci_stick "$(printf '%064d' 0)" >ci.out 2>&1
check "c-import refuses a public.asc that differs from the paper digest" '[ $? -ne 0 ] && grep -q "not the copy you last wrote down" ci.out && ! GNUPGHOME=$T/mac4 gpg --list-keys 2>/dev/null | grep -q pub'
GNUPGHOME=$T/mac4 sh "$D/c-import.sh" "$F" ci_stick "$dg" >ci.out 2>&1
check "c-import accepts a public.asc that matches the paper digest" '[ $? -eq 0 ] && GNUPGHOME=$T/mac4 gpg --list-keys 2>/dev/null | grep -q pub'
GNUPGHOME=$T/mac4 gpgconf --kill all 2>/dev/null
# renewal session: the typed fingerprint decides which key the RAM keyring is built for
mkdir -p rs rs2
YKHK_STATE=$T/rs sh "$D/renew-start.sh" "$spaced" ci_stick >rs.out 2>&1
check "renew-start builds the keyring from the stick for the typed fingerprint" '[ $? -eq 0 ] && [ "$(cat rs/primary.fpr)" = "$F" ] && GNUPGHOME=$(cat rs/gnupghome) gpg --list-keys "$F" >/dev/null 2>&1'
YKHK_STATE=$T/rs2 sh "$D/renew-start.sh" "$other" ci_stick >rs.out 2>&1
check "renew-start refuses a fingerprint that is not the stick's key" '[ $? -ne 0 ] && [ ! -f rs2/primary.fpr ]'
mkdir -p rs3 rs4
YKHK_STATE=$T/rs3 sh "$D/renew-start.sh" "$F" ci_stick "$(printf '%064d' 0)" >rs.out 2>&1
check "renew-start refuses a public.asc that differs from the paper digest" '[ $? -ne 0 ] && grep -q "not the copy you last wrote down" rs.out && [ ! -f rs3/primary.fpr ]'
YKHK_STATE=$T/rs4 sh "$D/renew-start.sh" "$F" ci_stick "$dg" >rs.out 2>&1
check "renew-start accepts the paper digest" '[ $? -eq 0 ] && [ "$(cat rs4/primary.fpr)" = "$F" ]'
for r in rs rs2 rs3 rs4; do [ -f $r/gnupghome ] && {
  GNUPGHOME=$(cat $r/gnupghome) gpgconf --kill all 2>/dev/null
  rm -rf "$(cat $r/gnupghome)"
}; done
gpgconf --kill all 2>/dev/null
unset GNUPGHOME
reset

# 6b. need_init seeds the plan from next to the scripts
mkdir -p seedtest && cp "$D/lib.sh" seedtest/ && printf '1\troot\troot\t1\t5.7.4\tyes\n' >seedtest/devices.tsv && printf '. "$(dirname "$0")/lib.sh"\nneed_init\n' >seedtest/t.sh
YKHK_STATE=$T/seeded sh seedtest/t.sh >/dev/null 2>&1
check "need_init seeds devices.tsv from next to the scripts" '[ -s seeded/devices.tsv ]'
rm -f seedtest/devices.tsv
YKHK_STATE=$T/unseeded sh seedtest/t.sh >/dev/null 2>&1
check "need_init dies without a plan" '[ $? -ne 0 ]'

# 6c. verify.sh: read-only precondition checks
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
reset
sh "$D/verify.sh" >vf.out 2>&1
check "verify passes a clean plan with no markers" '[ $? -eq 0 ] && grep -q "next ceremony step: B0" vf.out'
touch st/done.B2
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails a marker that skips an earlier step" '[ $? -ne 0 ] && grep -q "step B2 is marked done but B0 is not" vf.out'
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n2\troot\tnano\t222\t5.7.4\tno\n' >st/devices.tsv
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails two root keys" '[ $? -ne 0 ] && grep -q "2 root keys" vf.out'
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\troot\t222\t5.7.4\tyes\n' >st/devices.tsv
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails duplicate labels" '[ $? -ne 0 ] && grep -q "duplicate labels" vf.out'
printf '1\troot\tRoot_1\t111\t5.7.4\tyes\n' >st/devices.tsv
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails a label outside [a-z0-9-]" '[ $? -ne 0 ] && grep -q "invalid label" vf.out'
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tread\n' >st/devices.tsv
touch st/done.A1
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails A1 marked done with an unverified key" '[ $? -ne 0 ] && grep -q "not verified: nano" vf.out'
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv

# 6d. the genuineness gate: a key that was not confirmed genuine is refused everywhere downstream
col() { awk -F'\t' -v l="$1" -v c="$2" '$3==l {print $c}' st/devices.tsv; }
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tread\n' >st/devices.tsv
sh "$D/verify.sh" >vf.out 2>&1
check "verify fails a plan with an unconfirmed key and no markers" '[ $? -ne 0 ] && grep -q "keys not confirmed genuine (phase A): nano" vf.out'
echo 222 >"$STUB/serial"
ans '\ny\ny\n'
sh "$D/b1-pins.sh" nano >b1.out 2>&1
check "ask_card refuses a key that was not confirmed genuine" '[ $? -ne 0 ] && grep -q "was not confirmed genuine" b1.out && [ ! -f st/done.B1.nano ]'
mkdir -p ustick
sh "$D/usb-prepare.sh" ustick >up2.out 2>&1
check "usb-prepare refuses a plan with an unconfirmed key" '[ $? -ne 0 ] && grep -q "not confirmed genuine" up2.out && [ ! -d ustick/scripts ]'
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
touch st/done.A1
sh "$D/key-read.sh" nano >kr.out 2>&1
check "key-read puts the key back to read and clears A1" '[ ! -f st/done.A1 ] && [ "$(col nano 6)" = read ]'
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t-\t-\tno\n' >st/devices.tsv
ans 'y\n\nn\n'
sh "$D/10-verify-keys.sh" >vk.out 2>&1
check "10-verify-keys resets a key that was reported not genuine" '[ $? -ne 0 ] && grep -q "Its row is reset" vk.out && [ "$(col nano 4)" = - ] && [ "$(col nano 6)" = no ]'
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
reset

# 7. usb-prepare
printf '1\troot\troot\t111\t5.7.4\tyes\n' >st/devices.tsv.keep
cp st/devices.tsv st/devices.tsv.orig
mkdir -p stick/scripts
touch stick/._junk stick/scripts/._x
sh "$D/usb-prepare.sh" "$T/stick" >up.out 2>&1
check "usb-prepare copies byte-identical scripts" 'cmp -s "$D/lib.sh" stick/scripts/lib.sh && cmp -s "$D/go.sh" stick/scripts/go.sh && cmp -s st/devices.tsv stick/scripts/devices.tsv'
check "usb-prepare writes a manifest and prints its digest" '[ -s stick/scripts/SHA256SUMS ] && grep -Eq "Manifest digest .*: [0-9a-f]{64}" up.out'
shacheck() { if command -v sha256sum >/dev/null 2>&1; then (cd stick/scripts && sha256sum "$@"); else (cd stick/scripts && shasum -a 256 "$@"); fi; }
check "the manifest digest in the output is the digest of SHA256SUMS" '[ "$(shacheck SHA256SUMS | cut -d" " -f1)" = "$(sed -n "s/.*Manifest digest .*: //p" up.out)" ]'
check "the manifest verifies the copied scripts and the plan" 'shacheck -c SHA256SUMS >/dev/null 2>&1 && grep -q " devices.tsv$" stick/scripts/SHA256SUMS && grep -q " lib.sh$" stick/scripts/SHA256SUMS'
printf "# tampered\n" >>stick/scripts/go.sh
check "a one-byte change to a copied script fails the manifest" '! shacheck -c SHA256SUMS >/dev/null 2>&1'
cp "$D/go.sh" stick/scripts/go.sh
check "usb-prepare removes ._ files" '[ ! -e stick/._junk ] && [ ! -e stick/scripts/._x ]'
check "usb-prepare copies every script" '[ "$(ls "$D"/*.sh | wc -l)" -eq "$(ls stick/scripts/*.sh | wc -l)" ]'
check "usb-prepare finds no key material in its own scripts" 'grep -q "Stick ready" up.out'

# 8. c-check (the card must match the record AND belong to the key imported under the typed fingerprint)
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
echo 222 >"$STUB/serial"
printf '%s\n' "PIN tries remaining:        3
Reset code tries remaining: 3
Admin PIN tries remaining:  3
$daily_ok" >"$STUB/pgpinfo"
printf 'PIN:                          8 attempt(s) remaining\nCredential storage remaining: 99\n' >"$STUB/fidoinfo"
sub() { awk '/^subkey\(/ {print $2}' ci_stick/ceremony-record.txt | sed -n "${1}p"; }
c1=$(sub 1)
c2=$(sub 2)
c3=$(sub 3)
good="$c1 $c2 $c3"
f1=$(printf '%040d' 1 | tr 0 B)
f2=$(printf '%040d' 2 | tr 0 C)
f3=$(printf '%040d' 3 | tr 0 D)
foreign="$f1 $f2 $f3"
{
  echo "primary: $F"
  echo "card(nano): $good"
} >rec.txt
{
  echo "primary: $F"
  echo "card(nano): $foreign"
} >rec_forged.txt
printf 'primary: %s\n' "$F" >rec_nocard.txt
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check passes a correct Nano" '[ $? -eq 0 ] && grep -q "all checks passed" cc.out && grep -q "PASS card subkeys belong to the imported identity" cc.out'
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$c1 $c2 $f3" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check fails on mismatching card fingerprints" '[ $? -ne 0 ] && grep -q "FAIL card subkeys match the record" cc.out'
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$foreign" sh "$D/c-check.sh" rec_forged.txt >cc.out 2>&1
check "c-check fails a card the record names but the imported key does not own" '[ $? -ne 0 ] && grep -q "FAIL card subkeys belong to the imported identity" cc.out'
GNUPGHOME=$T/mac2 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check fails when the record's primary is not imported and trusted" '[ $? -ne 0 ] && grep -q "not imported and trusted" cc.out'
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec_nocard.txt >cc.out 2>&1
check "c-check fails when the record has no card line" '[ $? -ne 0 ] && grep -q "FAIL no card(nano) line" cc.out'
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" "$T/missing.txt" >cc.out 2>&1
check "c-check fails when the record file is missing" '[ $? -ne 0 ] && grep -q "FAIL no card(nano) line" cc.out'
# an installed SSH key must be a FIDO2 key (the real ssh-keygen is needed: the stub prints a fixed line)
mkdir -p "$HOME/.ssh"
rm -f "$HOME/.ssh/id_ed25519_sk_nano" "$HOME/.ssh/id_ed25519_sk_nano.pub" # the b8 test left stub files here
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check skips the SSH check when no key is installed" 'grep -q "SKIP no SSH key" cc.out && grep -q "all checks passed" cc.out'
printf '%s\n' "sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fAAAABHNzaDo= synthetic-test-key" >"$HOME/.ssh/id_ed25519_sk_nano.pub"
GNUPGHOME=$T/mac1 PATH=$T/realbin:$PATH YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check passes an installed ED25519-SK key" '[ $? -eq 0 ] && grep -q "PASS SSH key nano is a FIDO2 key" cc.out'
"$T/realbin/ssh-keygen" -q -t ed25519 -N "" -f "$T/plain" >/dev/null 2>&1
cp "$T/plain.pub" "$HOME/.ssh/id_ed25519_sk_nano.pub"
GNUPGHOME=$T/mac1 PATH=$T/realbin:$PATH YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check fails a plain software key installed as the SSH key" '[ $? -ne 0 ] && grep -q "FAIL SSH key nano is not an ED25519-SK key" cc.out'
rm -f "$HOME/.ssh/id_ed25519_sk_nano.pub"
sed -i.bak 's/Once/Always/' "$STUB/pgpinfo"
GNUPGHOME=$T/mac1 YKHK_CARD_FPRS="$good" sh "$D/c-check.sh" rec.txt >cc.out 2>&1
check "c-check fails when the signature PIN is Always" '[ $? -ne 0 ] && grep -q "FAIL signature PIN" cc.out'
for h in mac1 mac2; do GNUPGHOME=$T/$h gpgconf --kill all 2>/dev/null; done

# 9. B1 precondition: no keys on a card before its PINs changed
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
touch st/done.B0 st/done.B2 st/done.B5
echo 111 >"$STUB/serial"
sh "$D/b6-keytocard.sh" >b6g.out 2>&1
check "b6 refuses a root card whose PINs were not changed" '[ $? -ne 0 ] && grep -q "step B1.root is not done" b6g.out'
echo 222 >"$STUB/serial"
sh "$D/b3-subkeys.sh" nano >b3g.out 2>&1
check "b3 refuses a daily card whose PINs were not changed" '[ $? -ne 0 ] && grep -q "step B1.nano is not done" b3g.out'

# 10. assert-card.sh: read-only card-state assertion after a step (go.sh calls it)
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n2\tdaily\tnano\t222\t5.7.4\tyes\n' >st/devices.tsv
echo 222 >"$STUB/serial"
pins() { printf 'PIN tries remaining:        %s\nReset code tries remaining: %s\nAdmin PIN tries remaining:  %s\n' $1 $2 $3; }
{
  pins 3 3 3
  printf '%s\n' "$daily_ok"
} >"$STUB/pgpinfo"
printf 'PIN:                          8 attempt(s) remaining\nCredential storage remaining: 99\n' >"$STUB/fidoinfo"
: >"$STUB/calls"
sh "$D/assert-card.sh" B1.nano >as.out 2>&1
check "assert B1 passes with 3 3 3 counters" '[ $? -eq 0 ] && grep -q "PASS" as.out'
check "assert never writes to the card" '! grep -q -e "change-" -e "set-" -e "delete" -e "reset" "$STUB/calls"'
{
  pins 3 3 2
  printf '%s\n' "$daily_ok"
} >"$STUB/pgpinfo"
sh "$D/assert-card.sh" B1.nano >as.out 2>&1
check "assert B1 fails on a spent PIN counter" '[ $? -ne 0 ] && grep -q "FAIL PIN counters" as.out'
{
  pins 3 3 3
  printf '%s\n' "$daily_ok"
} >"$STUB/pgpinfo"
echo 111 >"$STUB/serial"
sh "$D/assert-card.sh" B1.nano >as.out 2>&1
check "assert fails when another key is plugged in" '[ $? -ne 0 ] && grep -q "FAIL key" as.out'
echo 222 >"$STUB/serial"
{
  pins 3 3 3
  printf '%s\n' "$daily_ok" | sed 's/Once/Always/'
} >"$STUB/pgpinfo"
sh "$D/assert-card.sh" B7.nano >as.out 2>&1
check "assert B7 fails when the signature PIN is Always" '[ $? -ne 0 ] && grep -q "FAIL signature PIN" as.out'
{
  pins 3 3 3
  printf '%s\n' "$daily_ok"
} >"$STUB/pgpinfo"
sh "$D/assert-card.sh" B7.nano >as.out 2>&1
check "assert B7 passes the daily policy" '[ $? -eq 0 ]'
printf 'FPRS FPRE FPRA\n' >st/card.nano
YKHK_CARD_FPRS='FPRS FPRE FPRA' sh "$D/assert-card.sh" B3.nano >as.out 2>&1
check "assert B3 passes when the card holds the recorded subkeys" '[ $? -eq 0 ]'
YKHK_CARD_FPRS='FPRS FPRE OTHER' sh "$D/assert-card.sh" B3.nano >as.out 2>&1
check "assert B3 fails on a different subkey" '[ $? -ne 0 ] && grep -q "FAIL card subkeys" as.out'
echo 111 >"$STUB/serial"
echo ROOTFPR >st/primary.fpr
mkdir -p gh && echo "$T/gh" >st/gnupghome
printf 'Signature key:\n  Touch policy: On\nDecryption key:\n  Touch policy: Off\nAuthentication key:\n  Touch policy: Off\n' >"$STUB/pgpinfo"
YKHK_CARD_FPRS='ROOTFPR' sh "$D/assert-card.sh" B6 >as.out 2>&1
check "assert B6 passes when the root card holds the primary" '[ $? -eq 0 ]'
YKHK_CARD_FPRS='OTHERFPR' sh "$D/assert-card.sh" B6 >as.out 2>&1
check "assert B6 fails when the card holds another key" '[ $? -ne 0 ] && grep -q "FAIL primary key" as.out'
sh "$D/assert-card.sh" B4a >as.out 2>&1
check "assert skips a step that holds no card" '[ $? -eq 0 ] && grep -q SKIP as.out'
# go.sh stops on a failed assertion
reset
printf '1\troot\troot\t111\t5.7.4\tyes\n' >st/devices.tsv
touch st/done.B0
{ pins 3 3 2; } >"$STUB/pgpinfo"
ans 'y\ny\ny\n' # each step script reopens the answer file from its start
sh "$D/go.sh" >gs.out 2>&1
check "go.sh stops when the card state does not match after a step" '[ $? -ne 0 ] && grep -q "FAIL PIN counters" gs.out && grep -q "card state" gs.out'

cd /
rm -rf "$T"
exit $fail
