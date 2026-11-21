# Known gaps

Solved gotchas are written into the step they affect (`ceremony.md`, `daily-machine.md`, the scripts). What stays here is
unverified. Update it during a real run with the exact command, tool version and result.

## Verified in a real run

Tails 7.17 with `ykman` 5.6.1 and GnuPG 2.4.x; YubiKey 5C, 5C Nano, 5C NFC on firmware 5.7.4; macOS with nixpkgs OpenSSH 10.5.
FIDO2 `ssh-keygen -t ed25519-sk` works on Tails. `ykman openpgp access set-signature-policy once` exists and works.

## Unverified

| Area                                      | Gap                                                                                                                                                                | How to check                                                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `card_fprs`                               | Reads the `fpr:` line of `gpg --card-status --with-colons` as sign, encrypt, authenticate. Not run against a card yet.                                             | `gpg --card-status --with-colons \| grep ^fpr`. `b3-subkeys.sh` stops if it does not return three values. |
| gpg menu automation                       | `key-attr`, `addcardkey` and `keytocard` stay manual: scripting menus is brittle across GnuPG versions and was not tested on a card. The scripts check the result. | Compare against a real run before automating.                                                             |
| `set-touch -a`                            | `b7-touch.sh` passes the Admin PIN with `-a` when `set-touch --help` lists it, otherwise `ykman` prompts per command.                                              | `ykman openpgp keys set-touch --help`.                                                                    |
| Why `addcardkey` wants the User PIN       | Seen twice. The reason is not confirmed.                                                                                                                           | Read the pinentry title each time.                                                                        |
| PIN cache lifetime                        | Whether `gpg-agent`'s `default-cache-ttl` affects card PINs is unmeasured. The card session (`Once`) is what holds the PIN.                                        | After a replug, count PIN windows over a work session.                                                    |
| `ControlPersist`                          | GitHub's server-side idle timeout is unknown.                                                                                                                      | Run two `git` commands 10 minutes apart and count prompts.                                                |
| `quick-set-expire` on card-backed subkeys | Tested on software subkeys only.                                                                                                                                   | Run it on the real identity and list.                                                                     |
| Phone flows                               | NFC for GitHub 2FA and OpenPGP over NFC on Android untested. iOS OpenPGP on this card is unsupported.                                                              | Test on the actual phone and browser.                                                                     |
| Windows                                   | Unsupported.                                                                                                                                                       | A candidate build must pass the full set in `team.md`.                                                    |

- **SOPS cosign identity.** `references/sops-kms.md` pins the SOPS release workflow (`release.yml` at a `v` tag). The workflow
  file exists upstream, but the pattern was not run against a real release bundle. A mismatch fails closed.
- **ykman cache.** `nix_bin` caches the store path of `ykman` in the state dir until it is garbage collected or the file
  `nixbin.ykman` is deleted, so the version can lag nixpkgs.

## Design limits to state to users

- GitHub cannot tell hardware keys from software keys. The control is discipline.
- A live attacker on an unlocked machine can still ask the card to sign. The touch policy limits silent use.
- `ssh` with `verify-required` cannot cache the PIN. A reused connection trades the touch for convenience.
- The Admin PIN in `b7-touch.sh` reaches `ykman` as an argument and shows in `ps` for a moment. This assumes an airgapped,
  single-user session.
- A cached OpenPGP touch stays valid for about 15 seconds.
- Nothing closes the GnuPG PIN cache automatically.
- The ADC refresh token for KMS is a software credential and widens the trust boundary beyond the key.
- A handle made from the card is useless without the key, PIN and touch, but it exposes a credential ID. A file that only
  looks like a handle is a different matter: check the key type (`ED25519-SK`) and the fingerprint against the paper from B8.

## Version floors

- YubiKey firmware 5.7.4 or later (advisories in `sources.md`).
- GnuPG 2.2 or later, OpenSSH 8.4 or later (`verify-required`), `ykman` 5.x syntax.
- SOPS: pin one approved release and verify its signatures before use.
