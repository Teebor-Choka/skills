---
name: yubikey
description: >
  Set up, verify or repair YubiKey-backed SSH, GPG, FIDO2 and commit signing. Use only when
  the user asks. Not for OTP, PIV or smart-card login, other tokens, or generic SSH key rotation.
license: MIT
compatibility: any
metadata:
  version: "0.2.0"
---

# YubiKey hardware keys

Set up one identity so that no private key exists in cleartext on any disk. Each daily YubiKey generates its
own signing, encryption, and authentication subkeys on the card. A third YubiKey holds the certify-only primary key and
stays offline. SSH uses separate FIDO2 resident keys. The only secret that touches storage is a passphrase-encrypted
backup of the primary key.

The agent coaches and verifies. The human holds every secret. This split is the main design constraint.

**Privacy warning.** Prefer an air-gapped local model for this work, and tell the user so before the first step. Everything
the agent sees goes into its session: fingerprints, device serial numbers, the identity, file paths and every command
output. No PIN or passphrase passes through the agent, but the rest is exactly what an attacker would want to learn.
A hosted model is acceptable only if the user accepts that exposure.

## Operating contract

- Never ask for, read, log, or store a PIN, Admin PIN, Reset Code, passphrase, or recovery code. The user types them at the
  prompt. If a user pastes one anyway, do not repeat it.
- The agent has no terminal for prompts. Scripts that prompt run in the user's own terminal window (or on Tails). In
  session, the agent asks each physical confirmation through the question dialog and runs only the non-interactive scripts.
- Before every physical action (plug, unplug, touch, format, flash, write), wait for the user's answer. Never chain steps.
- Ask for explicit confirmation immediately before each irreversible command: `keytocard`, `revkey`, `ykman openpgp reset`,
  `ykman fido reset`, key-attribute changes on a card that holds keys, primary-key revocation, destroying a backup.
- Follow every step with a scripted, read-only check of the preconditions for the next one: `scripts/verify.sh` for the
  plan and the step markers, and `scripts/c-check.sh` for a plugged-in key. Continue only on PASS. Never trust a
  recollection: a claim that a step is done needs the read-back or the script's own check.
- Use full 40-character fingerprints. Treat stray strings that look like `cccccd…` typed into a reply as noise from a touched
  key's OTP slot, and re-ask.
- A prompt that names no secret is a guess. Ask the user to read the window title, or for a photo, before they type.
- Format of every step to the user: a short explainer, the physical steps as a numbered list, then the progress bar
  (`scripts/progress.sh`).

## Who runs what

| Where                          | Who                            | Scripts                                                                                                                       |
| ------------------------------ | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Daily machine, in session      | agent, after each confirmation | `init-plan.sh`, `key-read.sh`, `key-genuine.sh`, `tails-fetch.sh`, `usb-prepare.sh`, `c-import.sh`, `c-check.sh`, `verify.sh` |
| Daily machine, user's terminal | user                           | `00-init.sh`, `10-verify-keys.sh` (prompting wrappers of the in-session scripts)                                              |
| Tails, offline                 | user, no agent                 | `go.sh`, which runs `b0` to `b9` in order                                                                                     |

State lives in `${XDG_STATE_HOME:-~/.local/state}/yubikey-hw-keys/` (override `YKHK_STATE`), with no secrets: `devices.tsv`
(index, role, label, serial, firmware, verified), `done.<step>` markers, fingerprints. `YKHK_TTY` redirects prompt input,
for tests. Every script resolves its tool from `PATH` and otherwise from nixpkgs through nix, resolved once per session.

## Inputs to settle first

Ask only for what is missing:

1. Scope: solo (default) or team (`references/team.md`).
2. Daily OS: run `uname -s` first. `Darwin` is macOS. For `Linux`, read `/etc/os-release`. Ask only when that is unclear.
   Windows is out of scope.
3. A laptop that boots Tails (x86-64 only). Stop here if none exists.
4. Identity: query the user, with defaults where available: `git config user.email`, and for GitHub the verified emails
   of the account (`gh api user/emails`), GitHub being the default source. Confirm the exact `Name <email>`. For commits
   to show as verified, the email must match a verified email at the Git host.
5. Secrets encryption with a KMS (optional, skippable). `references/sops-kms.md` documents SOPS with Google Cloud KMS
   (a project, billing and KMS rights). Another KMS, such as OpenBao, follows the same pattern: ask which one exists.
6. Hardware: one root key and two daily keys from the YubiKey 5 series, firmware 5.7.4 or later (read it with
   `ykman info`; the `ykman` tool itself needs 5.x), and three USB sticks (1: 8 GB or more for Tails; 2: LUKS for the
   backup; 3: FAT for the public key and these scripts).
7. How many USB ports are free. One is enough: Tails keeps its port. The encrypted backup is exported to memory first
   (`b4-backup.sh`) and then copied to each stick in turn (`b4-copy.sh`). With both sticks attached the flow is the
   same and only faster.

## Quick start

1. Ask Claude to set up YubiKey hardware keys. It asks the inputs below, then walks the phases in order.
2. Phase A, on your online Mac: plug each key in once so Claude reads its serial and firmware, then confirm each is genuine.
3. Phase B, offline: boot Tails from stick 1, check the scripts against the paper digest, run `sh ~/scripts/go.sh`. It prompts for every PIN and passphrase.
4. Phase C, back on the Mac: import the public key, run the checks, register the keys on GitHub.
5. Phase E can wait. Do the GitHub 2FA keys, recovery codes and `ykman otp delete 1` on the NFC key later; `references/daily-machine.md` and `references/recovery.md` list the steps.

Type PINs and passphrases only in your own terminal or on Tails, never in the chat.

## Phases

Each phase has an exit check. Do not start the next phase until it passes.

1. **A. Prepare** (online machine; `references/ceremony.md` part A). Exit: all three keys genuine with firmware 5.7.4 or
   later; Tails image verified and flashed; Tails stick has Persistent Storage with only Additional Software and
   Persistent Folder, `ykman` installed; sticks 2 and 3 formatted (Quick erase); `usb-prepare.sh` verified stick 3 and the user wrote its manifest digest on paper.
2. **B. Ceremony** (Tails, offline; part B). The user checks `~/scripts` against the paper digest with `sha256sum`, then runs
   `sh ~/scripts/go.sh`. Exit: `go.sh` reports completion, which
   means: both backups restored (B5) before the primary key moved (B6); six subkeys, all with an expiry; touch policies
   read back; one SSH key per daily key; handles and fingerprints on stick 3.
3. **C. Daily machine** (`references/daily-machine.md`). Exit: `c-import.sh` (with the fingerprint from the paper record
   of B2) and `c-check.sh` pass for every key; `ssh -T`
   greets the user with each key; GitHub shows the keys, the GPG key, and two security keys with recovery codes saved; a
   test signed commit shows `Good signature`.
4. **D. SOPS and KMS** (optional; `references/sops-kms.md`).
5. **E. Recovery readiness** (`references/recovery.md`). Exit: the user can say where the root key, stick 1, stick 2 and
   the recovery codes are, and has read the loss runbook once.

## Failure handling

- A restore test fails (B5): stop. Do not run `keytocard`. The RAM keyring is the only copy of the primary key.
- A PIN counter dropped: stop and find out which prompt was answered. Read the counters (`ykman openpgp info`,
  `ykman fido info`, no PIN needed) before any retry. FIDO2 allows 8 tries, OpenPGP User and Admin PIN 3.
- A subkey has no expiry before B4: the B4 gate refuses. Use `subkey-expiry.sh PERIOD FPR...`.
- A tool or output differs from the references: read `references/known-gaps.md`, check `--help` on the installed version,
  and record the difference there.
- Firmware below 5.7.4: stop. The unit cannot be updated. Replace it.

## Done means

- Three keys with PINs changed before any key material existed.
- Primary key on the root card, two tested encrypted backups with an independent passphrase.
- Six on-card subkeys with an expiry, two independent FIDO2 SSH keys, both registered on GitHub.
- A verified SSH login and a verified signature from each daily key.
- GitHub 2FA with both keys and saved recovery codes.
- The user can state where each recovery item is stored.

## References

| File                          | Read when                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `references/ceremony.md`      | Preparing or running the ceremony, or answering "which window wants which secret". |
| `references/daily-machine.md` | After the ceremony: tools, import, SSH, GitHub, Git signing, daily habits.         |
| `references/sops-kms.md`      | The user wants secrets encryption with a KMS (SOPS with Google Cloud KMS).         |
| `references/recovery.md`      | A key is lost, broken or stolen, or a subkey expires or needs a new date.          |
| `references/team.md`          | Scope is a team: registry, release gate, offboarding, rehearsal.                   |
| `references/known-gaps.md`    | A step behaves differently than written, or before publishing changes.             |
| `references/sources.md`       | Citing or re-checking a claim.                                                     |

`tests/rehearse-ceremony.sh` and `tests/rehearse-steps.sh` rehearse the scripts with stubs and a software keyring (no card).
Run both after any script change.
