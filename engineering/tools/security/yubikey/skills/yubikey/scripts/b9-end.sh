#!/bin/sh
# B9: save the SSH handles and fingerprints to the PUBLIC stick, kill gpg, print the storage rules.
. "$(dirname "$0")/lib.sh"
need_init
for m in B0 B2 B4 B5 B6; do need_done "$m"; done
for l in $(all_labels); do
  need_done "B1.$l"
  need_done "B7.$l"
done
for l in $(daily_labels); do need_done "B8.$l"; done
PUBLIC=${YKHK_PUBLIC_DIR:-/media/amnesia/PUBLIC}
while [ ! -d "$PUBLIC" ] || [ ! -w "$PUBLIC" ]; do
  pause "Unplug the YubiKey, plug in the PUBLIC stick and wait for it to mount at $PUBLIC"
  [ -d "$PUBLIC" ] && [ -w "$PUBLIC" ] || {
    say "$PUBLIC is not mounted."
    confirm "Try again?" || die "stopped"
  }
done
mkdir -p "$PUBLIC/ssh"
cp "$YKHK_STATE"/ssh/* "$PUBLIC/ssh/" || die "copy failed"
for f in "$YKHK_STATE"/ssh/*; do cmp -s "$f" "$PUBLIC/ssh/$(basename "$f")" || die "$f differs after copy"; done
for l in $(daily_labels); do
  echo "ssh($l): $(ssh-keygen -l -f "$YKHK_STATE/ssh/id_ed25519_sk_$l.pub" | awk '{print $2, $NF}')"
done >>"$PUBLIC/ceremony-record.txt"
sync
gpgconf --kill all 2>/dev/null || true
say "Saved: $(find "$PUBLIC/ssh" -type f | sed 's|.*/||' | tr '\n' ' ')"
say "Write this on paper too: public.asc digest $(sha "$PUBLIC/public.asc" | cut -d' ' -f1). Every later session checks the stick against it."
say ""
say "Shut Tails down from the system menu. Remove every key and stick. Store apart:"
say "  root key | stick 1 (Tails, holds a backup bundle) | stick 2 (BACKUP). Never the root key with a backup."
say "Keep: the daily keys, and the PUBLIC stick for the Mac."
mark_done B9
