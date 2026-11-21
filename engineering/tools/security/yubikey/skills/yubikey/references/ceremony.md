# Ceremony: prepare, provision, hand over

Part A runs on a trusted online machine, with the agent. Part B runs on Tails with one command. Replace `Name <email>`
with the identity the user confirmed.

> **Note on the email.** If the keys will sign commits for a Git host, the email in `Name <email>` must match a verified
> email on the user's account there (for GitHub: Settings, Emails). Otherwise commits show as unverified.

## Contents

- Why Tails, and why offline
- Part A: prepare (online machine)
- Part B: the ceremony (Tails, offline)
- Prompt guide: which window wants which secret
- Manual gpg menus, and what to pick

## Why Tails, and why offline

The primary key is the root of the identity. While the ceremony runs it exists in cleartext in memory, and anything that
can read the memory or the storage of the machine could copy it. Tails runs from a USB stick, works in RAM, leaves nothing
on the disks of the host, and forgets everything at shutdown, so the daily operating system, with its software and its
history, never takes part. Offline mode removes the network as a way out while the key exists in memory. After B6 the
primary key lives on the root card, and the only other copy is the passphrase-encrypted backup.

## Part A: prepare

**A1. Verify the keys.** One key plugged in at a time, packaging sealed. In session: `init-plan.sh COUNT`, then per key
`key-read.sh LABEL` (serial, firmware 5.7.4 or later, no duplicate serial), the Yubico genuineness page
(https://www.yubico.com/genuine/, needs WebAuthn, so a normal browser), then `key-genuine.sh LABEL`. Every later step refuses a key that was not confirmed genuine, `usb-prepare.sh` refuses a plan
with one, and a re-read of a key puts it back to unconfirmed: repeat the genuineness page after any re-read.

**A2. Tails stick (stick 1).** `tails-fetch.sh` downloads the current image and checks sha256 and the OpenPGP signature
against the pinned primary fingerprint. Write it with balenaEtcher. Check the target device first: the write erases it.
Tails boots on x86-64 only.

**A3. First Tails boot, online (the x86-64 laptop).**

1. Welcome Screen, Additional Settings: set an Administration Password (Tails forgets it at shutdown).
2. Create the Persistent Storage with a strong passphrase. Enable **only** Additional Software and Persistent Folder.
   GnuPG, SSH Client and Dotfiles persistence can keep secret key data. The dialog has no confirm button: switches save
   at once and apply at the next boot. After a restart, check
   `sudo cat /live/persistence/TailsData_unlocked/persistence.conf` for `.gnupg`, `.ssh`, `dotfiles` (none may appear).
3. `sudo apt update && sudo apt install yubikey-manager pcscd`. Accept the offer to keep them. Check `ykman --version`.
4. Disks: format stick 2 as Ext4 with LUKS (label `BACKUP`) and stick 3 as FAT (label `PUBLIC`). Choose **Don't overwrite
   existing data (Quick)**: the other erase option writes the whole stick (an hour for 62 GB) and the dialog cannot cancel it.
   If it is already running, unplug the stick. The whole stick as one volume is fine.
5. Shut down.

**A4. Fill stick 3 (on the online machine).** `usb-prepare.sh` copies every script and `devices.tsv` to `PUBLIC/scripts`,
removes OS metadata files such as `._*`, compares byte for byte, scans for key material and writes `SHA256SUMS`. It prints
the digest of that manifest: write it on paper next to the B2 fingerprint. Eject the stick.

Plan for the ports: Tails stays in its port the whole time (removing the boot stick ends the session). With one free
port, keys and sticks take turns there. The scripts ask for each swap.

## Part B: the ceremony (Tails, offline)

1. Boot stick 1, unlock the Persistent Storage, Additional Settings, **Offline Mode, Disable all networking**.
2. Plug in stick 3 and check what is on it before anything runs. The scripts on the stick are not trusted until you
   have compared them with the digest you wrote down in A4:

   ```
   cp -r /media/amnesia/PUBLIC/scripts ~/scripts
   cd ~/scripts && sha256sum SHA256SUMS     # must equal the digest on paper, character for character
   sha256sum -c SHA256SUMS                  # every line must say OK
   ```

   Run `sh ~/scripts/go.sh` only when both checks pass. The check must use the tools of Tails: a check inside the stick's
   own scripts could be faked by a tampered copy. Copying matters too: unplugging stick 3 later would remove scripts
   running from it.

3. `go.sh` shows a progress bar and the next step, asks, runs it, reads the card back with `assert-card.sh` (no PIN, no
   write), and repeats. A failed step or a card that does not match stops with its message. Run
   `go.sh` again to continue. Nothing is retyped except passphrases and menu answers.

| Step | Script                                                        | What it does and checks                                                                                                                                                                |
| ---- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B0   | `b0-start.sh`                                                 | Refuses if a network route exists. RAM keyring with `disable-ccid`.                                                                                                                    |
| B1   | `b1-pins.sh LABEL`                                            | Only the named key plugged in (by serial). `ykman` sets User PIN, Admin PIN, Reset Code. Daily keys also FIDO2 PIN and OTP slot 1 removal.                                             |
| B2   | `b2-primary.sh`                                               | Certify-only ed25519 primary key. Refuses a second one.                                                                                                                                |
| B3   | `b3-subkeys.sh LABEL`                                         | Refuses a card that already holds keys. Curve25519 attributes, three on-card subkeys, expiry required. Records the card's fingerprints.                                                |
| B4   | `b4-backup.sh`, then `b4-copy.sh backup`, `b4-copy.sh public` | Refuses unless all six subkeys exist and have an expiry. Encrypted bundle to RAM stage and Persistent, then one stick at a time. `b4-backup-all.sh` is the one-shot variant for a hub. |
| B5   | `b5-verify-backup.sh`                                         | Blocking. Restores both bundles, compares all seven fingerprints, certifies a test key.                                                                                                |
| B6   | `b6-keytocard.sh`                                             | Refuses before B5. Moves the primary key to the root card, then checks for `sec>`.                                                                                                     |
| B7   | `b7-touch.sh LABEL`                                           | Root: signature touch On. Daily: Cached, Off, Off and signature PIN Once. Reads the card back and fails on a mismatch.                                                                 |
| B8   | `b8-ssh.sh LABEL`                                             | FIDO2 resident `ed25519-sk` key with `verify-required`. Handle kept in RAM.                                                                                                            |
| B9   | `b9-end.sh`                                                   | Saves handles and fingerprints to the PUBLIC stick, kills gpg, prints storage rules.                                                                                                   |

Store the root key, stick 1 and stick 2 in three separate places. The root key never sits with a backup.

## Prompt guide

Read each window title before you type. A wrong PIN costs a try: User PIN 3, Admin PIN 3, FIDO2 PIN 8.

| Step            | Window                    | Secret                                                                                                                                              |
| --------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1              | `ykman` prompts           | current, then new PIN                                                                                                                               |
| B3 `key-attr`   | Admin PIN                 | Admin PIN of that key                                                                                                                               |
| B3 `addcardkey` | titled just "PIN"         | OpenPGP **User PIN**, not the Admin PIN (seen twice)                                                                                                |
| B3, B4, B6      | names your key            | primary passphrase. It repeats: export and certification each unlock the key. `abc` shows what you typed.                                           |
| B4              | no key named, asked twice | the new **backup passphrase** (independent of every other secret)                                                                                   |
| B5              | no key named              | backup passphrase. It may not appear if `gpg-agent` cached it. Test independence with `gpgconf --kill all` then `gpg --decrypt BUNDLE > /dev/null`. |
| B6              | Admin PIN                 | root key's Admin PIN                                                                                                                                |
| B7              | script prompt             | Admin PIN of that key, once                                                                                                                         |
| B8              | prompt, then touch        | FIDO2 PIN (a wrong PIN here also hits the 8-try counter)                                                                                            |

## Manual gpg menus, and what to pick

The scripts print this at the right moment. Menu numbering differs between GnuPG versions, so pick by the label.

- `gpg --card-edit`, `admin`, `key-attr`: for Signature, Encryption, Authentication choose **ECC**, then **Curve 25519**.
  `key-attr` writes at once. There is no `save` in `--card-edit`.
- `gpg --edit-key`, `addcardkey`: pick the key type, validity `1y` or `2y`. **Never choose "never expires"**: the B4 gate
  rejects it, and fixing it later needs the root card (`recovery.md`). End with `save`.
- `keytocard`: answer `y`, pick the Signature slot, `save`. GnuPG notes that the local secret key is deleted by `save`.
  That is the RAM copy, and both backups already restored in B5.
- `gpg --gen-revoke` (inside `b4-backup.sh`) refuses batch mode. Answer `y`, `0`, an empty line, `y`.
