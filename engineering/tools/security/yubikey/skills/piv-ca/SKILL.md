---
name: piv-ca
description: >
  Hold an offline certificate authority root key on two YubiKeys (PIV). Generate it on Tails with no
  network, sign the intermediate CA in that session, import the same key into both YubiKeys with PIN
  and touch on every use, then destroy the file. Use when setting up a private PKI root, moving a CA
  key onto hardware, or asking whether one YubiKey can hold several keys. Not for OpenPGP, SSH, FIDO2
  or commit signing (use the yubikey skill), not for an online issuing CA, whose key stays on its
  server, and not for rotating a root (no cross-signing steps here).
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# CA root key on two YubiKeys

A private PKI has a root CA that signs one intermediate and then stays offline. This skill puts the root key on
two YubiKeys so that no copy exists on any disk after one offline session. The intermediate keeps issuing online
and is not covered here.

The agent coaches and checks. The human holds every secret and runs every command on the Tails machine. The agent
has no access to that machine. The commands and the reasoning are in `references/runbook.md`.

## Operating contract

- Never ask for, read, log or store a PIN, PUK or management key. The user types them at the prompt of `ykman`.
  Never pass them on the command line (`--pin`, `-P`, `--puk`, `-p`, `--new-pin`, `-n`, `--new-puk`,
  `--new-management-key`, `-m`): arguments show in `ps`. If a user pastes one, do not repeat it.
- Wait for the user's answer before each physical action (plug, unplug, touch, power off). Never chain steps.
- Ask for explicit confirmation immediately before each irreversible command: signing the intermediate,
  `ykman piv keys import`, `ykman piv keys delete`, `ykman piv reset`, and `shred` of the key file.
- After each step the user runs its read-only check from the runbook and reads back the output. The agent
  compares it with the expected output. Continue only when it matches. A claim that a step is done needs the
  read-back, not a recollection.
- The key file exists only in RAM on Tails, only for this session, and never on the plain USB stick.
- Say before the first step that everything the user relays goes into the agent's session: serial numbers,
  subject names, paths and command output. An air-gapped local model avoids that. Ask the user to relay only
  what a check needs.

## Decide first

| Input                                   | Why it matters                                                                                                                                         |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Names the intermediate may sign         | Becomes the DNS `nameConstraints` of the intermediate. It does not constrain IP, email or URI names unless you exclude them (the runbook excludes IP). |
| Root and intermediate lifetimes         | Root: ten years is common. Intermediate: shorter, two years is common.                                                                                 |
| Where the public root certificate lives | Every client must trust it, so it goes in a repo or a trust-store package.                                                                             |
| Who holds each YubiKey                  | Separate places. Losing both means a new root and re-trusting every client.                                                                            |
| Whether the YubiKeys use PIV already    | `ykman piv reset` wipes every PIV slot, not only 9c. Use a YubiKey whose PIV is empty.                                                                 |

## Phases

1. **Prepare** (online): two genuine YubiKeys on firmware 5.7.4 or later, a Tails stick with `yubikey-manager`
   and `pcscd` kept in Persistent Storage, a plain USB stick, and the intermediate's CSR. Exit: the CSR verifies.
2. **Session** (Tails, offline): check the network is off, check the tools, generate the root, sign the CSR with
   the name constraint, load and verify each YubiKey, copy out public files and check the copy, destroy the key
   file, power off. Exit: `ykman piv certificates import --verify` passed on each YubiKey.
3. **Ship**: verify the chain on the daily machine, publish the root certificate, load the chain into the issuing CA.
4. **Recovery readiness**: both YubiKeys stored apart, PIV PINs and PUKs recorded, the loss rule written down.

## One YubiKey, many keys

PIV, OpenPGP and FIDO2 keep separate keys, PINs and slots. Putting the CA root in PIV slot 9c touches neither the
OpenPGP keys nor the FIDO2 credentials. `ykman piv reset` clears PIV only, but all of it: slots 9a, 9d, 9e and the
retired slots too.

## Not verified

State these to the user. Do not present them as tested.

- Signing a later intermediate from the YubiKey needs a PKCS#11 path (`libykcs11` from `yubico-piv-tool`, used
  by OpenSSL through a PKCS#11 provider). Package names and module path on Tails are unchecked. The first signing
  in the runbook does not depend on it. Without that path a later intermediate cannot be signed.
- The `ykman` options were read from `ykman` 5.9.1 `--help` and not run on a card. The prompts and the text of
  `ykman piv info` are from memory. Tails may ship an older `ykman`, so the runbook checks the options on Tails
  first.
- The `openssl` commands ran on OpenSSL 3.6.3. The OpenSSL version on Tails is unchecked.

## References

| File                    | Read when                                                               |
| ----------------------- | ----------------------------------------------------------------------- |
| `references/runbook.md` | Running the session: every command, expected output and stop condition. |
| `references/sources.md` | Citing or re-checking a claim.                                          |
