---
name: yubikey
description: >
  Set up, verify or repair YubiKey-backed SSH, GPG, FIDO2 and commit signing. Use only when
  the user asks. Not for OTP, PIV smart-card login, other tokens, or generic SSH key rotation. For an offline CA root key on PIV, use the piv-ca skill.
license: MIT
compatibility: any
metadata:
  version: "0.3.0"
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

Read `references/state.md` for where state lives, the `YKHK_*` overrides and tool resolution.

## Inputs to settle first

Ask only for what is missing. Read `references/inputs.md` for the seven inputs (scope, daily OS, Tails laptop, identity, KMS, hardware, USB ports) before the first step.

## Quick start

1. Ask Claude to set up YubiKey hardware keys. It asks the inputs, then walks the phases in order.
   Read `references/quick-start.md` for the per-phase summary (steps 2 to 5) when the user asks for the overview.

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
4. **D. SOPS and KMS** (optional, skippable; the `sops-kms` skill holds it and its exit check). Phase E does not wait for D.
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

Read `references/state.md` for the full done-means list; every item must hold before the work is called done.

## References

| File                          | Read when                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `references/ceremony.md`      | Preparing or running the ceremony, or answering "which window wants which secret". |
| `references/daily-machine.md` | After the ceremony: tools, import, SSH, GitHub, Git signing, daily habits.         |
| `references/recovery.md`      | A key is lost, broken or stolen, or a subkey expires or needs a new date.          |
| `references/team.md`          | Scope is a team: registry, release gate, offboarding, rehearsal.                   |
| `references/known-gaps.md`    | A step behaves differently than written, or before publishing changes.             |
| `references/sources.md`       | Citing or re-checking a claim.                                                     |

`tests/rehearse-ceremony.sh` and `tests/rehearse-steps.sh` rehearse the scripts with stubs and a software keyring (no card).
Run both after any script change.
