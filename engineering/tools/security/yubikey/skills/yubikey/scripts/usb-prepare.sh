#!/bin/sh
# Mac side: copy the ceremony scripts and the device plan to the PUBLIC stick, verify, remove macOS clutter.
# Usage: usb-prepare.sh [DIR]   (default /Volumes/PUBLIC). Non-interactive. Eject afterwards: diskutil eject DIR
# Writes SHA256SUMS next to the scripts and prints the digest of that manifest. The user writes the digest on paper and
# checks the copied scripts against it on Tails, with Tails' own sha256sum, before go.sh runs. A check inside the
# scripts would not help: a tampered copy can fake it.
. "$(dirname "$0")/lib.sh"
need_init
unverified=$(unverified_labels | tr '\n' ' ')
[ -z "$unverified" ] || die "keys not confirmed genuine: $unverified. Finish phase A first."
dir=${1:-/Volumes/PUBLIC}
[ -d "$dir" ] && [ -w "$dir" ] || die "$dir is not mounted and writable"
src=$(cd "$(dirname "$0")" && pwd)
dest="$dir/scripts"
mkdir -p "$dest"
rm -f "$dest"/*.sh "$dest/devices.tsv"
{ cp "$src"/*.sh "$dest"/ && cp "$YKHK_STATE/devices.tsv" "$dest/devices.tsv"; } || die "copy failed"
sync
find "$dir" -name '._*' -exec rm -f {} + 2>/dev/null || true
rm -f "$dest/SHA256SUMS"
# shellcheck disable=SC2046 # file names have no spaces
(cd "$dest" && sha $(printf '%s\n' *.sh devices.tsv | LC_ALL=C sort)) >"$dest/SHA256SUMS" || die "could not write the manifest"
digest=$(cd "$dest" && sha SHA256SUMS | cut -d' ' -f1)
bad=0
for f in "$src"/*.sh; do cmp -s "$f" "$dest/$(basename "$f")" || {
  say "DIFF $f"
  bad=1
}; done
cmp -s "$YKHK_STATE/devices.tsv" "$dest/devices.tsv" || {
  say "DIFF devices.tsv"
  bad=1
}
[ "$bad" -eq 0 ] || die "verification failed"
if grep -rl -e '-----BEGIN PGP PRIV''ATE KEY' -e '-----BEGIN OPENSSH PRIV''ATE KEY' "$dest" >/dev/null 2>&1; then die "key material found in $dest"; fi
say "Stick ready: $(find "$dest" -type f | wc -l | tr -d ' ') files in $dest, byte-identical, no key material."
say ""
say "Manifest digest (write it on paper next to your B2 fingerprint): $digest"
say "On Tails, before go.sh: cp -r $dest ~/scripts && cd ~/scripts && sha256sum SHA256SUMS   (must equal the paper digest)"
say "then: sha256sum -c SHA256SUMS   (every line OK), and only then: sh ~/scripts/go.sh"
