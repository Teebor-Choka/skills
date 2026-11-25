# SOPS with Google Cloud KMS

SOPS encrypts each file data key to two Cloud KMS keys, one in Europe and one in the United States. Cloud IAM controls
who can use them.

**Trust boundary.** The YubiKey protects the Google sign-in in the browser. It does not approve each KMS call once local
Application Default Credentials (ADC) exist. The ADC refresh token is a software credential in
`$HOME/.config/gcloud/application_default_credentials.json`. Any process that can read it has your IAM permissions.
Require full-disk encryption. Say this limit out loud to the user before they start.

## Prerequisites

The person who owns the Google Cloud project must provide:

1. A dedicated project with an active billing account.
2. For the provisioning operator: `roles/serviceusage.serviceUsageAdmin` and `roles/cloudkms.admin`.
3. A managed group for key users, for example `secrets-users@example.org`. Use a group, not individual bindings.
4. Audit logging and billing alerts.

## Install SOPS

Use the release the user or team has approved. Check the current release and its signatures at
https://github.com/getsops/sops/releases before pinning a version.

- macOS: `brew install sops cosign slsa-verifier` (use `brew install --cask google-cloud-sdk` for gcloud). This installs
  the current release and runs none of the checks below. Compare `sops --version` with the approved release.
- Debian/Ubuntu: install `cosign` and `slsa-verifier` first. Neither is in the Debian archive. Use the signed releases of
  sigstore/cosign and slsa-framework/slsa-verifier, verified as their release pages describe, or your workstation
  management. Then download the SOPS binary and verify it before install: `cosign verify-blob` on the checksum file,
  `sha256sum -c`, and `slsa-verifier verify-artifact` against the `.intoto.jsonl` provenance.

  Save the block as `install-sops.sh` and run it with `bash install-sops.sh`. It stops at the first failed check, so
  `sudo install` runs only when every check passed. Do not paste the block into an interactive shell: `set -e` would end
  that shell, and without it a failed check would not stop the install.

```bash
set -eu
for tool in curl cosign sha256sum slsa-verifier; do
  command -v "$tool" >/dev/null || { echo "missing $tool: install it first" >&2; exit 1; }
done
SOPS_VERSION=REPLACE_WITH_APPROVED_VERSION
SOPS_ARCH=$(dpkg --print-architecture)   # amd64 or arm64 only
SOPS_ARTIFACT="sops-v${SOPS_VERSION}.linux.${SOPS_ARCH}"
SOPS_BASE="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}"

curl -fLO "${SOPS_BASE}/${SOPS_ARTIFACT}"
curl -fLO "${SOPS_BASE}/sops-v${SOPS_VERSION}.checksums.txt"
curl -fLO "${SOPS_BASE}/sops-v${SOPS_VERSION}.checksums.sigstore.json"
curl -fLO "${SOPS_BASE}/sops-v${SOPS_VERSION}.intoto.jsonl"

cosign verify-blob "sops-v${SOPS_VERSION}.checksums.txt" \
  --bundle "sops-v${SOPS_VERSION}.checksums.sigstore.json" \
  --certificate-identity-regexp='^https://github.com/getsops/sops/\.github/workflows/release\.yml@refs/tags/v' \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com
sha256sum -c "sops-v${SOPS_VERSION}.checksums.txt" --ignore-missing
slsa-verifier verify-artifact "$SOPS_ARTIFACT" \
  --provenance-path "sops-v${SOPS_VERSION}.intoto.jsonl" \
  --source-uri github.com/getsops/sops \
  --source-tag "v${SOPS_VERSION}"
sudo install -m 0755 "$SOPS_ARTIFACT" /usr/local/bin/sops
```

Any failed check stops the script before `sudo install`. The `cosign` identity is the SOPS release workflow. If `cosign`
rejects it for a release you approved, inspect the certificate and fix the pattern: do not loosen it to a bare
organization match.

Read back: `sops --version` prints the approved release.

## Create the KMS keys

Replace both placeholders. Run the loop one region at a time: set `location` to one region and run its body, then repeat.

```bash
GCP_PROJECT=replace-with-project-id
KEY_USERS_GROUP=replace-with-key-user-group@your-domain
gcloud config set project "$GCP_PROJECT"
gcloud services enable cloudkms.googleapis.com

for location in europe-west1 us-central1; do
  gcloud kms keyrings create sops --location "$location"
  gcloud kms keys create secrets --location "$location" \
    --keyring sops --purpose encryption
  gcloud kms keys add-iam-policy-binding secrets \
    --location "$location" --keyring sops \
    --member "group:${KEY_USERS_GROUP}" \
    --role roles/cloudkms.cryptoKeyEncrypterDecrypter
done
```

Read back, for each region:

```bash
gcloud kms keys list --location europe-west1 --keyring sops
gcloud kms keys list --location us-central1 --keyring sops
```

Expect the key `secrets` in each, with state `ENABLED`.

## Configure the repository

`.sops.yaml` in the repository root. Replace `PROJECT_ID`. Do not commit the placeholder.

```yaml
creation_rules:
  - path_regex: ^secrets/.*\.ya?ml$
    gcp_kms: "projects/PROJECT_ID/locations/europe-west1/keyRings/sops/cryptoKeys/secrets,projects/PROJECT_ID/locations/us-central1/keyRings/sops/cryptoKeys/secrets"
```

When the KMS list changes, run `sops updatekeys secrets/prod.yaml` for every existing file. Review the diff. Check that
both resource IDs appear in the SOPS metadata.

## Credentials

```bash
gcloud auth application-default login
```

To revoke on a machine that you still control: `gcloud auth application-default revoke`. For a lost laptop, revoke
through the account response process. IAM changes are eventually consistent. Treat access as live until a denial test
fails. Denial test, run as the user or machine whose access was removed:

```bash
sops --decrypt secrets/prod.yaml > /dev/null
```

Expect a permission error from Cloud KMS, not a decrypt.

## Create and edit a file without cleartext on disk

Create new encrypted output from stdin. The temporary file holds only encrypted data.

```bash
if test -e secrets/prod.yaml; then
  echo "Target already exists: secrets/prod.yaml"
  exit 1
fi
encrypted_tmp=$(mktemp)
if printf '{}\n' \
    | sops --encrypt --input-type yaml --output-type yaml \
        --filename-override secrets/prod.yaml \
    > "$encrypted_tmp"; then
  mv "$encrypted_tmp" secrets/prod.yaml
else
  echo "SOPS encryption failed; the target was not created."
  exit 1
fi
```

Edit with `sops secrets/prod.yaml`. Read with `sops --decrypt` or `sops exec-env secrets/prod.yaml 'your-app'`, in a
pipe or controlled terminal. Never redirect decrypted output to a file in a repository. Add `*.dec.yaml` and
`secrets/*.plain.*` to `.gitignore`. Check every SOPS change for cleartext before commit:

```bash
git diff --cached -- secrets/
```

Read it. Expect every value as `ENC[...]` and a `sops:` block that lists both KMS resource IDs. Stop if a value is clear.
