---
name: sops-kms
description: >
  Encrypt repository secrets with SOPS, keyed by Google Cloud KMS or OpenBao transit: install SOPS, create
  keys, write `.sops.yaml`, set credentials, edit without cleartext on disk, revoke access. Use for SOPS,
  `.sops.yaml`, Cloud KMS key rings, OpenBao transit keys for SOPS, `sops updatekeys`, and ADC or token
  revocation. Not for YubiKey, OpenPGP, SSH or FIDO2 (use the yubikey skill), not for a PIV certificate
  authority (use the piv-ca skill), not for other SOPS backends (AWS KMS, age, PGP).
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# SOPS with Google Cloud KMS or OpenBao

SOPS encrypts each file's data key with key-management keys. Cloud IAM or an OpenBao policy decides who can use them.
This skill was split out of the `yubikey` skill, where it was optional phase D. It needs no YubiKey. A YubiKey can
protect the sign-in that unlocks it. Commands and read-backs: `references/runbook.md`.

## Operating contract

The operating contract of the `yubikey` skill applies: the privacy warning, no secrets in the chat, a wait before each
action, a read-back before a step counts as done. These rules are specific to SOPS:

- State the trust boundary before the user starts. Google: after `gcloud auth application-default login`, the refresh
  token in `$HOME/.config/gcloud/application_default_credentials.json` has the user's IAM permissions, and a YubiKey
  does not approve each KMS call. OpenBao: `VAULT_TOKEN` has the policy of its token. Require full-disk encryption.
- Never read, print or log that credential file, a token, or decrypted output.
- Confirm immediately before each command or block that changes the cloud project, OpenBao, the machine or the encrypted
  data. Google: `gcloud config set project`, `gcloud services enable`, the key loop (one region at a time, a
  confirmation per region), `gcloud auth application-default login`, and `... revoke`. OpenBao: `bao secrets enable`,
  `bao write`, `bao policy write`, `bao token revoke`. Both: `sudo install` and `sops updatekeys`.
- Debian: the runbook verifies the SOPS release. macOS: `brew install` runs no signature check and takes no pin, so say
  so and have the user compare `sops --version` with the approved release. Do not loosen the `cosign` identity pattern to
  a bare organization match.
- OpenBao addresses are `https` with certificate verification. Plain `http` is for the local test only.

## Decide first

| Input                                | Why it matters                                                              |
| ------------------------------------ | --------------------------------------------------------------------------- |
| Backend: Google Cloud KMS or OpenBao | Picks the runbook path. One backend per repository.                         |
| Who owns the project or cluster      | The owner provides the provisioning rights and a managed key-user group.    |
| The SOPS release to pin              | The runbook has a placeholder. On Debian do not install an unpinned latest. |
| Where the encrypted files live       | Becomes the `path_regex` of `.sops.yaml`.                                   |

## Phases

1. **Prerequisites.** Google: project with billing, provisioning roles, key-user group, audit logging, billing alerts.
   OpenBao: reachable over TLS, rights to enable an engine and write a policy, a login method.
2. **Install SOPS** with the signature and provenance checks. Exit: every check passed before `sudo install`.
3. **Create the keys.** Google: two regions, group bound. OpenBao: transit mount, two keys, a policy. Exit: the key
   list shows both keys.
4. **Configure the repository.** `.sops.yaml` with both key references. Exit: no placeholder is committed.
5. **Credentials, create, edit.** Exit: an encrypted file exists and the staged diff shows only `ENC[...]` values.
6. **Revocation readiness.** The user can revoke on a machine they control and has seen the denial test fail as expected.

## Verified and not verified

State both lists to the user.

Run: the OpenBao path, by `tests/openbao.sh` (21 checks, all passed) against a throwaway local dev server: SOPS 3.13.3,
OpenBao 2.6.6, plain HTTP, userpass login. It covers the keys, the policy, encrypt, decrypt, the permission denials,
a revoked token, a second key, and `updatekeys`.

Not run:

- Anything on the Google Cloud KMS path, including `gcloud kms keys list`. The expected output in the runbook
  (`ENABLED`) was written from memory of the tool, not read from its documentation or observed.
- The Debian install block, and the `cosign` identity pattern for the SOPS release workflow (`release.yml` at a `v`
  tag) against a real release bundle. A mismatch fails closed.
- OpenBao with TLS, with OIDC or any login method but userpass, with a second key on another cluster, or on a
  production cluster.

## References

| File                    | Read when                                               |
| ----------------------- | ------------------------------------------------------- |
| `references/runbook.md` | Running any phase: every command and its read-back.     |
| `references/sources.md` | Citing or re-checking a claim.                          |
| `tests/openbao.sh`      | Re-running the OpenBao rehearsal (needs bao, sops, jq). |
