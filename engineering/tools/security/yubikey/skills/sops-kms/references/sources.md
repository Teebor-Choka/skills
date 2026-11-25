# Sources

Re-check time-sensitive details here before relying on them.

- SOPS releases: https://github.com/getsops/sops/releases
- Cloud KMS key creation: https://docs.cloud.google.com/kms/docs/create-encryption-keys
- Local ADC: https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment
- IAM propagation: https://docs.cloud.google.com/iam/docs/access-change-propagation
- SOPS repository (key backends, `hc_vault_transit_uri`): https://github.com/getsops/sops
- OpenBao transit secrets engine: https://openbao.org/docs/secrets/transit/
- OpenBao policies: https://openbao.org/docs/concepts/policies/
- Origin of the SOPS flow: "SSH, GPG, and SOPS with hardware-backed keys: HOPR minimum security baseline (v7)" by
  tolbrino (HOPR), https://gist.github.com/tolbrino/e6b86f2d2e0f163c4c714421208aeffa. Details in the `yubikey` skill's
  `references/sources.md`.
