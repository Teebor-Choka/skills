#!/bin/sh
# B8: create the FIDO2 resident SSH key on one daily key. Usage: b8-ssh.sh LABEL
# Handle and public key are kept in RAM, then saved to the PUBLIC stick by b9-end.sh.
. "$(dirname "$0")/lib.sh"
need_init
label=${1-}
[ -n "$label" ] || die "usage: b8-ssh.sh LABEL"
[ "$(label_role "$label")" = daily ] || die "$label is not a daily key"
[ -s "$YKHK_STATE/identity" ] || die "no identity recorded. Run b2-primary.sh first."
email=$(sed -n 's/.*<\(.*\)>.*/\1/p' "$YKHK_STATE/identity")
ask_card "$label"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
f="$HOME/.ssh/id_ed25519_sk_$label"
[ ! -e "$f" ] || die "$f already exists in this session"
say "FIDO2 PIN window or prompt, then touch the key when it blinks (maybe twice). Empty passphrase for the handle."
ssh-keygen -t ed25519-sk -O resident -O verify-required -C "$email ($label)" -f "$f" || die "ssh-keygen failed"
[ -s "$f" ] && [ -s "$f.pub" ] || die "handle files missing"
mkdir -p "$YKHK_STATE/ssh"
cp "$f" "$f.pub" "$YKHK_STATE/ssh/"
say "Fingerprint: $(ssh-keygen -l -f "$f.pub")"
say "Write this fingerprint, with its type, on paper next to your B2 fingerprint. The daily machine compares against the paper, not against the stick."
mark_done "B8.$label"
