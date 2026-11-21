# Sources

## Origin

Derived from "SSH, GPG, and SOPS with hardware-backed keys: HOPR minimum security baseline (v7)" by tolbrino (HOPR):
https://gist.github.com/tolbrino/e6b86f2d2e0f163c4c714421208aeffa. The guide's review date is 2026-07-31, and it is marked
draft until its controlled rehearsal passes. HOPR-specific names and the registry layout are generalized in this skill.

## Primary references

Re-check time-sensitive details here before relying on them.

- YSA-2024-03: https://www.yubico.com/support/security-advisories/ysa-2024-03/
- YSA-2025-02: https://www.yubico.com/support/security-advisories/ysa-2025-02/
- Yubico genuineness check: https://www.yubico.com/genuine/
- Tails installation and verification: https://tails.net
- Tails Persistent Storage: https://tails.net/doc/persistent_storage/configure/index.en.html
- OpenSSH release notes (`-sk` types in 8.2, `verify-required` in 8.4): https://www.openssh.com/releasenotes.html
- GnuPG manual: https://www.gnupg.org/documentation/manuals/gnupg/
- SOPS releases: https://github.com/getsops/sops/releases
- Cloud KMS key creation: https://docs.cloud.google.com/kms/docs/create-encryption-keys
- Local ADC: https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment
- IAM propagation: https://docs.cloud.google.com/iam/docs/access-change-propagation
- Bitwarden SSH agent: https://bitwarden.com/help/about-ssh/
- Bitwarden vault timeout: https://bitwarden.com/help/vault-timeout/
- Bitwarden login and unlock: https://bitwarden.com/help/understand-log-in-vs-unlock/
- GitHub passkeys: https://docs.github.com/en/authentication/authenticating-with-a-passkey/about-passkeys
- GitHub 2FA: https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa/configuring-two-factor-authentication
- GitHub commit verification: https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification
