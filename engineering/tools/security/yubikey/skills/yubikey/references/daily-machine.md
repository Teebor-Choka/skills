# Daily machine

Phase C, after the ceremony. The agent can run the read-only checks. The user types PINs in their own terminal.

## Contents

- Tools
- Import and check
- SSH
- GitHub
- Git signing
- Daily habits

## Tools

Needed: GnuPG 2.2 or later, OpenSSH 8.4 or later **with FIDO2**, `ykman`, a pinentry. On macOS, Apple's `/usr/bin/ssh` and
`ssh-keygen` cannot load FIDO2 keys ("Cannot download keys without provider"), so put a nixpkgs or Homebrew `openssh` ahead
of it. The nixpkgs OpenSSH 10.5 loads the provider. On Nix, add `openssh`, `gnupg` and `yubikey-manager` to `home.packages`.
On Debian or Ubuntu: `gnupg scdaemon pcscd yubikey-manager openssh-client pinentry-curses libu2f-udev`, with `pcscd` enabled and
`disable-ccid` in `~/.gnupg/scdaemon.conf` (otherwise `ykman` and GnuPG fight for the key: "card busy").

## Import and check

Plug in stick 3. Ask the user for the primary fingerprint they wrote down in B2 (paper or second device). Never read it
from the stick: the record and `public.asc` sit on the same writable stick, so a stick that was altered after the ceremony
agrees with itself. Then run `c-import.sh FINGERPRINT DIR DIGEST` (DIR is the stick, `/Volumes/PUBLIC`; DIGEST is the `public.asc` digest from your paper). It refuses unless that fingerprint equals the record's primary and
the one primary key in `public.asc`, and it checks the key count and subkey count in a throwaway keyring. It warns about
any subkey without expiry, imports the exact bytes it checked, and sets ultimate trust on the fingerprint you gave. The
primary key then shows `sec#` (secret absent), which is right.

After a replacement (`recovery.md`) the stick holds every subkey, the revoked ones included. `c-import.sh` expects six: set
`YKHK_SUBKEYS` to the total in `public.asc`, and list every subkey in `ceremony-record.txt`, or the import refuses.

Per key, no PIN needed: `c-check.sh` reads the plugged-in key and checks PIN counters (3 3 3), touch policy (root: signature On;
daily: Cached Off Off), signature PIN Once, FIDO2 PIN attempts 8, a stored FIDO2 credential, and the card's subkey fingerprints
against the record. The record sits on the writable stick, so a match is not enough: the card's subkeys must also belong to the
key that `c-import.sh` imported under your paper fingerprint, otherwise a reset card with an edited record line would pass.
Run `c-import.sh` first. A daily key whose record has no `card(label)` line fails: a record that cannot vouch for a key
must not read as a pass. Plug in the PUBLIC stick, or pass a copy of the record. A counter below 3 or 8 means a wrong PIN was entered since the ceremony: stop and find out why.

`gpg --card-status` with each key links its subkeys: `gpg -K` then shows `ssb>` with the card serial.

## SSH

The card is the source of the SSH keys, not the stick. `ssh-keygen -K` (nixpkgs OpenSSH, in the user's terminal, FIDO2 PIN and
touch) writes a handle file `id_ed25519_sk_rk` and its `.pub` for each resident key. For each key:

1. Compare the fingerprint **and the type** (`ED25519-SK`) that `ssh-keygen -l -f id_ed25519_sk_rk.pub` prints with the one you
   wrote on paper in B8. Do not compare it with `ceremony-record.txt`: that file sits on the writable stick, which agrees with
   whatever was written on it. A plain software key swapped in for a handle prints another type.
2. Rename to `id_ed25519_sk_<label>`, mode 600, and upload only that `.pub` to GitHub. Never take a handle or a `.pub`
   from the stick, even if its fingerprint looks right.

`c-check.sh` also fails an installed `id_ed25519_sk_<label>.pub` that is not an `ED25519-SK` key. A handle holds the public key and a
credential ID, not a private key. ssh **rejects** a handle that is group or world readable, so a store symlink (0444) or a checkout
link (0644) fails with `UNPROTECTED PRIVATE KEY FILE`. Installing by copy with mode 600 (a home-manager activation step) lets a new
machine skip `ssh-keygen -K`: copy only files that `ssh-keygen -K` produced from the physical key, and check them as above.

Config: do not override `Host github.com` when other accounts use software keys on it. Add an alias:

```
Host github-yk
    HostName github.com
    User git
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_ed25519_sk_nano
    IdentityFile ~/.ssh/id_ed25519_sk_nfc
    AddKeysToAgent no
```

Test with the nixpkgs `ssh`: `ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_sk_nano -T git@github.com`. Expect the
`Hi <login>!` greeting after the touch and the FIDO2 PIN. Test both keys.

**Fewer prompts.** `verify-required` makes ssh ask for the PIN and a touch on every new connection, and no agent caches the PIN.
Reuse one connection: `ControlMaster auto`, `ControlPath ~/.ssh/cm-%C`, `ControlPersist 1h`. While the master is open, any process
in the session can open channels without a touch, even after the key is unplugged. Shorter is safer: 10 minutes covers a burst
of git commands, 1 hour covers a work session, hours trade away the touch requirement for most of a day.

## GitHub

1. Settings, Emails: the key's UID email must be verified, or commits show Unverified.
2. SSH and GPG keys, New SSH key, type **Authentication Key**, for each `.pub`. (Signing Key is for SSH commit signing, which
   this setup does not use.)
3. New GPG key: paste the armored export. Do not copy anything else in between (a copied title replaces the clipboard).
4. Two-factor: TOTP first (required before a security key), then register both daily keys as security keys, choosing the
   **security key** option and not iCloud Keychain. Download recovery codes: one encrypted copy in the password manager, one
   sealed on paper away from the keys.

GitHub cannot tell a hardware key from a software key: the hardware rule rests on the user.

## Git signing

Test without changing config:

```
export GPG_TTY=$(tty)
git -C "$T" -c gpg.format=openpgp -c gpg.program=gpg -c user.email=<uid email> \
  -c 'user.signingkey=<signing subkey fingerprint>!' -c commit.gpgsign=true commit --allow-empty -m test
git -C "$T" -c gpg.format=openpgp log --show-signature -1
```

Expect a User PIN window once, a touch, and `Good signature … [ultimate]`. A second commit within the card session needs only
a touch (signature PIN `Once`; the touch stays valid about 15 seconds, fixed by the firmware).

A user with software signing set globally cannot switch globally: other accounts' commits would show Unverified, and the commit
email must match the key's UID. Scope GPG signing with an `includeIf` per directory. The `!` pins one card: with the other
card plugged in, signing fails until `user.signingkey` changes.

## Daily habits

- The card forgets the verified PIN when it loses power. After a replug the first signature asks for the User PIN again.
- `gpgconf --kill all` before suspend closes the PIN cache and also resets the card session. Skipping it is convenient and
  leaves signing open to a touch while the key is plugged in.
- The signing touch cannot be cached for hours. The PIN session can.
- Subkeys expire. Renewal needs the root card (`recovery.md`). Set a calendar reminder.
- Full-disk encryption on the laptop.
