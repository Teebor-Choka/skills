---
name: sops-kms
description: >
  Encrypt secrets in a Git repository with SOPS and Google Cloud KMS: install and verify SOPS, create two
  KMS keys in two regions, write `.sops.yaml`, set up local credentials, create and edit encrypted files
  without cleartext on disk, and revoke access. Use when the user asks for SOPS, `.sops.yaml`, Cloud KMS
  key rings, `sops updatekeys`, or ADC revocation. Not for YubiKey, OpenPGP, SSH or FIDO2 setup (use the
  yubikey skill), not for a PIV certificate authority (use the piv-ca skill), and not for other secret
  managers or KMS products, which follow the same pattern but are not documented here.
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# SOPS with Google Cloud KMS

SOPS encrypts each file data key to two Cloud KMS keys, one in Europe and one in the United States. Cloud IAM decides
who can use them. This skill was split out of the `yubikey` skill, where it was optional phase D. It needs no YubiKey,
but a YubiKey protects the Google sign-in that unlocks it.

The commands and the reasoning are in `references/runbook.md`.

## Operating contract

- Say the trust boundary before the user enables this: after `gcloud auth application-default login`, the refresh token
  is a software credential in `$HOME/.config/gcloud/application_default_credentials.json`. Any process that can read it
  has the user's IAM permissions, and the YubiKey does not approve each KMS call. Require full-disk encryption.
- Never read, print or log `application_default_credentials.json` or any decrypted secret. Never paste decrypted output
  into the chat.
- Ask for explicit confirmation immediately before each command that changes the cloud project or the encrypted data:
  `gcloud kms keys create`, `add-iam-policy-binding`, `sops updatekeys`, and `gcloud auth application-default revoke`.
- Run the runbook's checks after each step and compare the output with what the runbook expects. A claim that a step is
  done needs that read-back.
- The user installs SOPS only from a release they or their team approved, with the signature checks of the runbook. Do
  not loosen the `cosign` identity pattern to a bare organization match.

## Decide first

| Input                           | Why it matters                                                                                |
| ------------------------------- | --------------------------------------------------------------------------------------------- |
| The project owner and the group | Someone else usually owns the Google Cloud project. Key users are a managed group, not users. |
| The SOPS release to pin         | The runbook has a placeholder. Do not install an unpinned latest.                             |
| Where the encrypted files live  | Becomes the `path_regex` of `.sops.yaml`.                                                     |

## Phases

1. **Prerequisites.** Project with billing, the provisioning roles, a key-user group, audit logging and billing alerts.
2. **Install SOPS** with the signature and provenance checks. Exit: every check passed before `sudo install`.
3. **Create the keys** in two regions and bind the group. Exit: both key IDs exist.
4. **Configure the repository.** `.sops.yaml` with both resource IDs. Exit: no placeholder is committed.
5. **Credentials, create, edit.** Exit: an encrypted file exists and a cleartext check of the change is clean.
6. **Revocation readiness.** The user can say how to revoke on a laptop they control and what to do for a lost laptop.

## Not verified

State these to the user. Do not present them as tested.

- The `cosign` identity pattern for the SOPS release workflow (`release.yml` at a `v` tag) was not run against a real
  release bundle. A mismatch fails closed.
- No rehearsal test covers these commands. The `yubikey` skill's rehearsals cover its scripts only.

## References

| File                    | Read when                                             |
| ----------------------- | ----------------------------------------------------- |
| `references/runbook.md` | Running any phase: every command and what it expects. |
| `references/sources.md` | Citing or re-checking a claim.                        |
