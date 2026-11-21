# Team add-on

Read only when the scope is a team. The solo flow does not need this file. The team adds one **ops owner** and
external controls that this skill describes but cannot implement.

## Roles

| Role      | Does                                                                                                                                             |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Ops owner | Buys hardware and sticks, hands them over sealed and blank, keeps the registry, KMS IAM, release signers, and offboarding.                       |
| Developer | Verifies their own hardware, runs their own ceremony, protects the root card and backups. Nobody else, ops included, touches their private keys. |

Ops never verifies, generates, or handles a developer's key material.

## Procurement and handover

- Buy from the vendor or an authorized reseller to one controlled address. Record the supplier and purchase reference.
- Three keys per developer (5C, 5C Nano, 5C NFC), plus 2 to 3 spares of each model for loss and firmware advisories.
  Firmware 5.7.4 or later. Return older units.
- Three new USB sticks per developer. Bring 2 to 3 shared x86-64 laptops for Tails.
- Hand over in person with the packaging sealed.
- GitHub cannot verify that a key is hardware-backed. The setup relies on developer discipline. State this plainly in
  the rollout.

## Registry

Keep a registry file (for example `KEYS.yaml`) and one public key file per developer in a protected repository.

```yaml
schema_version: 1
developers:
  - id: alice
    github_login: alice-gh
    gpg_primary_fingerprint: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    root:
      role: root
      model: YubiKey 5C
      serial: "10000001"
      firmware: 5.7.4
    daily_keys:
      - role: nano
        model: YubiKey 5C Nano
        serial: "10000002"
        firmware: 5.7.4
        gpg_subkeys:
          sign: BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
          encrypt: CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
          authenticate: DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD
        ssh_fingerprint: SHA256:replace-with-complete-ssh-fingerprint
      - role: nfc
        # same fields as nano, with its own serial, subkeys, and ssh_fingerprint
    additional_ssh_keys: []
release_signers:
  - alice
```

Quote fingerprints that YAML could read as numbers. Uppercase OpenPGP fingerprints and remove spaces.

A registry verifier enforces: `schema_version: 1`; unique developer ID and GitHub login; one root and exactly two daily
devices with roles `nano` and `nfc`; 40-hex OpenPGP fingerprints; a full `SHA256:` SSH fingerprint per daily key;
unique serials and credential fingerprints; firmware 5.7.4 or later; every release signer maps to one developer; each
public-key file matches its primary and six subkey fingerprints.

Every registry change needs a signed commit and two distinct maintainer approvals. The release gate reads only the
approved default-branch state, never a release branch or pull request.

## Release signing, 3 of N

A release needs valid signatures from at least three distinct authorized developers. A developer counts once, even with
both daily keys. Authorize at least four signers, so one absence does not block a release.

1. Build all artifacts. Create one immutable manifest: `sha256sum <artifacts> > SHA256SUMS`. Never edit it after the
   first signer receives it.
2. Each signer makes a detached signature named `SHA256SUMS.<developer-id>.<signing-fingerprint>.asc`:

   ```bash
   gpg --armor --detach-sign --local-user "$SIGNING_FPR!" \
     --output "SHA256SUMS.$DEV_ID.$SIGNING_FPR.asc" SHA256SUMS
   ```

3. The external gate verifies in a fresh GnuPG home that imports the approved `public-keys/*.asc`:

   ```bash
   VERIFY_HOME=$(mktemp -d); chmod 700 "$VERIFY_HOME"
   GNUPGHOME="$VERIFY_HOME" gpg --batch --import public-keys/*.asc
   GNUPGHOME="$VERIFY_HOME" gpg --batch --status-fd 1 --verify "$SIGNATURE_FILE" SHA256SUMS
   ```

   The gate must: require a zero exit status; parse the full fingerprint from `VALIDSIG`; reject `BADSIG`, `ERRSIG`,
   `NO_PUBKEY`, `EXPSIG`, `EXPKEYSIG`, `REVKEYSIG`, `KEYEXPIRED`, `SIGEXPIRED`, `KEYREVOKED`; require the filename
   fingerprint to equal the signing fingerprint and the `VALIDSIG` primary fingerprint to equal the mapped one; map the
   fingerprint through the registry to one developer and role, and require that ID to match the filename and appear in
   `release_signers`; deduplicate by developer ID; require three or more; run `sha256sum -c SHA256SUMS`; publish only
   verified files. A missing or ambiguous mapping fails the release. GitHub Verified labels never satisfy the gate.

## Organization settings

Require 2FA for every member. Require signed commits on protected branches. GitHub keeps Verified labels on old commits
after a key is revoked, so use the gate, not the label, for releases.

## Offboarding

1. Remove the developer ID from `release_signers`. Merge with two approvals.
2. Remove the developer from the KMS user group. Run a denial test after IAM propagates.
3. Revoke ADC and identity-provider sessions.
4. Remove the developer from the GitHub organization, teams, and repositories. Remove deploy keys, invitations, and
   token grants.
5. Rotate every shared secret the developer could read. IAM removal does not erase what they already learned.
6. Recover the issued devices or record verified destruction.

## Quarterly audit

1. Compare all OpenPGP and SSH fingerprints with the registry.
2. Verify the root card and both backup locations. Restore each backup in a fresh Tails RAM keyring.
3. Test SSH and GPG use from each daily key independently.
4. Check GnuPG cache values 3600 and 28800.
5. Check GitHub 2FA keys, passkeys, recovery-code custody, KMS group membership, and both KMS resource IDs.
6. Run the release-gate negative and threshold tests. Review SOPS and YubiKey advisories.

## Rehearsal before rollout

Treat the procedure as a draft until a controlled rehearsal passes on test identities, a test GCP project, and a test
GitHub repository. Cover: registry schema tests; gate tests (reject invalid, expired, revoked, missing, and ambiguous
signers, a modified manifest or artifact, and two-developer releases; accept three; count one developer once); one full
ceremony on one Linux and one macOS machine; restoring both backups; SSH and signing from each daily key; SOPS to both
KMS keys; every recovery path in `recovery.md`; offboarding until KMS access fails. Record commands, versions,
fingerprints, results, and failures, and have the security owner and ops owner sign the report.

## Optional: third SSH key in a password manager

A software SSH key in a password manager is an optional third credential. It never replaces the two hardware keys. The
private key then lives in the vault and process memory, malware in an unlocked session can use it, and each use needs no
touch. Use it only after a documented risk acceptance. If used, set the vault timeout trigger to _On system lock_ and
the action to _Log out_, so that the next access needs the full login and its FIDO2 factor.
