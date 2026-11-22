# State and done criteria

## State

State lives in `${XDG_STATE_HOME:-~/.local/state}/yubikey-hw-keys/` (override `YKHK_STATE`), with no secrets: `devices.tsv`
(index, role, label, serial, firmware, verified), `done.<step>` markers, fingerprints. `YKHK_TTY` redirects prompt input,
for tests. Every script resolves its tool from `PATH` and otherwise from nixpkgs through nix, resolved once per session.

## Done means

- Three keys with PINs changed before any key material existed.
- Primary key on the root card, two tested encrypted backups with an independent passphrase.
- Six on-card subkeys with an expiry, two independent FIDO2 SSH keys, both registered on GitHub.
- A verified SSH login and a verified signature from each daily key.
- GitHub 2FA with both keys and saved recovery codes.
- The user can state where each recovery item is stored.
