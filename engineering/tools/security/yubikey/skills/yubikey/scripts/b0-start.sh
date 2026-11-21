#!/bin/sh
# B0, on Tails, offline: make a RAM keyring and check tools. Run once per ceremony session.
. "$(dirname "$0")/lib.sh"
if command -v ip >/dev/null 2>&1 && [ -n "$(ip -4 route show default 2>/dev/null)" ]; then
  die "the network is up. Restart Tails and choose Additional Settings, Offline Mode, Disable all networking."
fi
command -v gpg >/dev/null 2>&1 || die "gpg not found"
command -v ykman >/dev/null 2>&1 || die "ykman not found. Unlock Persistent Storage with Additional Software on the Welcome Screen."
if grep -qs '^ID=tails' /etc/os-release && [ "$(stat -f -c %T "${TMPDIR:-/tmp}" 2>/dev/null)" != tmpfs ]; then
  die "${TMPDIR:-/tmp} is not RAM-backed. Do not continue."
fi
[ ! -s "$YKHK_STATE/gnupghome" ] || die "a ceremony keyring exists ($(cat "$YKHK_STATE/gnupghome")). Continue from the next step."
d=$(mktemp -d)
chmod 700 "$d"
printf 'disable-ccid\n' >"$d/scdaemon.conf"
printf '%s\n' "$d" >"$YKHK_STATE/gnupghome"
say "RAM keyring: $d"
say "gpg:   $(gpg --version | head -n1)"
say "ykman: $(ykman --version)"
mark_done B0
