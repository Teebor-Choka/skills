# Loss, recovery, renewal

Treat a missing device as compromised. A PIN and a touch policy reduce the risk. They do not replace the procedure.
Before any revocation or reset, read the command back to the user and get explicit confirmation.

## Contents

- One daily key lost or stolen
- Both daily keys lost or stolen
- Root card fails, still in your possession
- Root card lost or stolen
- Renew, change or stagger expiry

## Start every offline session with the root card

Every flow below that uses the root card (revoking subkeys, renewing, replacing a daily key) starts the same way, and
nothing on stick 3 is trusted until you have checked it against what you wrote on paper:

```bash
cp -r /media/amnesia/PUBLIC/scripts ~/scripts && cd ~/scripts
sha256sum SHA256SUMS      # must equal the manifest digest from A4, character for character
sha256sum -c SHA256SUMS   # every line OK
sh ~/scripts/renew-start.sh FINGERPRINT /media/amnesia/PUBLIC DIGEST   # from your paper: the B2 fingerprint and the public.asc digest
S=${YKHK_STATE:-$HOME/.local/state/yubikey-hw-keys}
export GNUPGHOME=$(cat "$S/gnupghome") KEYFPR=$(cat "$S/primary.fpr")
gpg --card-status         # with the root card plugged in
```

`renew-start.sh` builds the RAM keyring from `public.asc` and stops unless the stick holds exactly one primary key with
that fingerprint and the digest of `public.asc` equals the one on your paper. The digest matters because a stale genuine
copy (one made before a revocation) has the same fingerprints, so only a value kept off the stick can detect it. After it, `$GNUPGHOME` and `$KEYFPR` are set for the commands below.

## One daily key lost or stolen

Work on the other daily key meanwhile.

1. Remove the lost key's SSH authentication key from GitHub.
2. Remove its GitHub 2FA security-key registration, and its passkey if one exists.
3. Start an offline session with the root card (the block above).
4. List the subkeys and map them to the lost device by fingerprint:

   ```text
   gpg -K --with-subkey-fingerprints "$KEYFPR"
   gpg --edit-key "$KEYFPR"
   gpg> key <matching-subkey-number>
   gpg> revkey
   gpg> save
   ```

   Revocation is permanent. Repeat for the sign, encrypt, and authenticate subkeys of the lost device only. Check that
   the other device's subkeys remain valid.

5. Export the updated public identity. Replace the GitHub GPG key, and `public.asc` on stick 3. Write the new `public.asc`
   digest on paper (`sha256sum public.asc`), replacing the old one: the next session checks against it.
6. Provision a blank replacement daily key with fresh subkeys and a fresh resident SSH key (`ceremony.md`, B1 to B3, B7
   to B8). Never copy credentials from the remaining key.
7. Register the replacement on GitHub. Update the team registry if one exists (`team.md`).

If the key was in a lost laptop, also revoke that laptop's credentials, including ADC (`sops-kms.md`).

## Both daily keys lost or stolen

1. Recover the GitHub account with a recovery code. Do not rely on a passkey from either lost key.
2. Remove both SSH keys, both 2FA registrations, and both passkeys from GitHub.
3. Start an offline session with the root card (the block above) and revoke all six daily subkeys.
4. Provision two blank replacement keys. Register both on GitHub.
5. Generate new GitHub recovery codes. The used set is then invalid.
6. If the laptop is missing too, revoke ADC and active sessions.

## Root card fails, still in your possession

No identity rotation is needed if you hold the card and a tested backup exists.

```bash
KEYFPR=REPLACE_WITH_FULL_40_HEX_PRIMARY_FINGERPRINT
restore_home=$(mktemp -d)
restore_dir=$(mktemp -d)
chmod 700 "$restore_home"
gpg --decrypt /media/amnesia/BACKUP/identity-backup.tar.gpg \
  | tar -x -C "$restore_dir"
GNUPGHOME="$restore_home" gpg --import "$restore_dir/primary-secret.asc"
GNUPGHOME="$restore_home" gpg --import /media/amnesia/PUBLIC/public.asc
GNUPGHOME="$restore_home" gpg -K --with-subkey-fingerprints "$KEYFPR"
```

Compare the primary fingerprint with the paper record of B2 (never with the stick). Certify a throwaway identity as in
`ceremony.md`, B5. Then
`export GNUPGHOME="$restore_home"`, insert a blank root card, and repeat B6 and the root part of B7. Keep the failed
card controlled until you destroy it. If neither backup restores, rotate as below.

## Root card lost or stolen

A new card with the same primary key cannot invalidate the lost copy. Rotate the identity.

1. Restore the backup bundle in Tails RAM and export that `GNUPGHOME` (as above).
2. GnuPG puts a safety colon before an exported revocation certificate. Remove only that colon in RAM:

   ```bash
   awk '{ sub(/^:/, ""); print }' revoke.asc > revoke-import.asc
   gpg --import revoke-import.asc
   gpg --armor --export "$KEYFPR" > revoked-public.asc
   ```

3. Publish the revoked identity (GitHub and any keyserver or registry that holds it).
4. Run the full ceremony again for a new primary key and new backups.
5. On each daily key, reset **only** the OpenPGP applet: `ykman openpgp reset`. This deletes every OpenPGP key on that
   device. Check the device first. FIDO2 SSH keys live in another applet and survive the reset.
6. Change the PINs on every card first (`b1-pins.sh`; B3, B6 and B9 refuse without it), generate six new subkeys, move the new primary key to a blank root card.
7. Replace the GitHub GPG key and update every fingerprint in the registry.

## Renew, change or stagger expiry

A subkey's expiry sits in a binding signature made by the **primary key**. Only the primary key can change it, so this
needs the root card in an offline Tails session. (Before B6 in the first ceremony, the primary key is still in the RAM
keyring and no root card is needed.) The change never touches the daily cards or their private subkeys. A subkey that
already expired can be extended the same way.

Expiry argument: `1y`, `18m`, `90d`, `2w` or a date such as `2027-11-15`. Zero and `never` are refused: a subkey that never
expires cannot be retired when its revocation does not reach every verifier. Use `subkey-expiry.sh`, not a raw `gpg`
command: only the script enforces this.

1. Boot Tails offline, plug in stick 3, copy and check the scripts as in `ceremony.md` part B step 2, then run
   `sh ~/scripts/renew-start.sh FINGERPRINT`. FINGERPRINT is the primary fingerprint from your paper record. The script
   builds the RAM keyring from `public.asc` and stops unless the stick holds exactly that one primary key. Then plug in the
   root card and run `gpg --card-status`.
2. List the subkeys and copy the full 40-character fingerprint of each one to change:

   ```bash
   sh ~/scripts/subkey-expiry.sh
   ```

3. Set the new expiry. Name only the subkeys to change:

   ```bash
   sh ~/scripts/subkey-expiry.sh 2y SUBKEY_FPR_1 SUBKEY_FPR_2 SUBKEY_FPR_3
   ```

   The root card asks for its User PIN and a touch (`set-touch sig on`). The script refuses zero and `never`, refuses a
   fingerprint that is not a subkey (the primary key does not count), and fails when any subkey is still without expiry.

4. List again. Each changed `ssb` shows the new `[expires: ...]` date.
5. Export the updated public identity, put it on stick 3, replace the key on GitHub, write the new `public.asc` digest on paper
   and update `ceremony-record.txt`:

   ```bash
   gpg --armor --export "$(cat "$YKHK_STATE/primary.fpr")" > public.asc
   ```

6. On the daily machine, run `gpg --import public.asc` to pick up the new dates. The encrypted primary-key backup does not
   change.

**Stagger the two daily keys.** Give the Nano 1 year and the NFC key 2 years, so one valid daily key always exists while
the other is renewed. Do step 3 once per key, with that key's three fingerprints and its own period.

**Switch the active daily key** (for example, to the NFC key in a year). Use the NFC signing subkey fingerprint:

```bash
git config --global user.signingkey "NFC_SIGNING_SUBKEY_FPR!"
```

SSH needs no change: `~/.ssh/config` lists both handles, so either key works. Plug in the NFC key and run
`gpgconf --kill all` so `gpg-agent` picks up the other card.
