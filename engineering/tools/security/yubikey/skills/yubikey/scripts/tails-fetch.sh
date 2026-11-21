#!/bin/sh
# Non-interactive. Usage: tails-fetch.sh [OUTDIR]   (default ~/Downloads/tails)
# Downloads the current Tails USB image, checks size and sha256, then verifies the OpenPGP signature
# in a throwaway GnuPG home. The signing key fingerprint must match TAILS_FPR.
. "$(dirname "$0")/lib.sh"
TAILS_FPR=A490D0F4D311A4153E2BB7CADBB802B258ACD84F # https://tails.net/doc/about/openpgp_keys/
out=${1:-$HOME/Downloads/tails}
mkdir -p "$out"
cd "$out" || die "cannot enter $out"

meta=$(curl -fsS --max-time 30 https://tails.net/install/v2/Tails/amd64/stable/latest.json | tr -d ' \n') || die "cannot fetch release metadata"
url=$(printf '%s' "$meta" | grep -o '"url":"[^"]*\.img"' | head -n1 | cut -d'"' -f4)
sha=$(printf '%s' "$meta" | grep -o '"sha256":"[0-9a-f]*","size":[0-9]*,"url":"[^"]*\.img"' | head -n1 | cut -d'"' -f4)
[ -n "$url" ] && [ -n "$sha" ] || die "could not parse the image URL or checksum"
img=${url##*/}
say "Image: $img"

if [ ! -f "$img" ]; then
  curl -fL --retry 3 -o "$img.part" "$url" || die "download failed"
  mv "$img.part" "$img"
fi
got=$(shasum -a 256 "$img" | cut -d' ' -f1)
[ "$got" = "$sha" ] || die "sha256 mismatch: got $got, expected $sha"
say "sha256 ok"

curl -fsSL -o "$img.sig" "https://tails.net/torrents/files/$img.sig" || die "cannot fetch signature"
curl -fsSL -o tails-signing.key https://tails.net/tails-signing.key || die "cannot fetch signing key"
GNUPGHOME=$(mktemp -d)
export GNUPGHOME
chmod 700 "$GNUPGHOME"
gpg --batch --quiet --import tails-signing.key 2>/dev/null
gpg --batch --with-colons --fingerprint 2>/dev/null | awk -F: '/^fpr:/ {print $10}' | grep -qx "$TAILS_FPR" ||
  die "signing key fingerprint is not $TAILS_FPR. Compare with https://tails.net/doc/about/openpgp_keys/"
# VALIDSIG: field 3 is the signing (sub)key, the last field is the primary key fingerprint.
gpg --batch --status-fd 1 --verify "$img.sig" "$img" 2>/dev/null |
  awk -v p="$TAILS_FPR" '$2=="VALIDSIG" && $NF==p {ok=1} $2~/^(BADSIG|ERRSIG|REVKEYSIG)$/ {bad=1} END {exit !(ok && !bad)}' ||
  die "signature check failed"
say "OpenPGP signature ok (key $TAILS_FPR)"
say "Verified image: $out/$img"
