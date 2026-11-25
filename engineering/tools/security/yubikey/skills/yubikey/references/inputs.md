1. Scope: solo (default) or team (`references/team.md`).
2. Daily OS: run `uname -s` first. `Darwin` is macOS. For `Linux`, read `/etc/os-release`. Ask only when that is unclear.
   Windows is out of scope.
3. A laptop that boots Tails (x86-64 only). Stop here if none exists.
4. Identity: query the user, with defaults where available: `git config user.email`, and for GitHub the verified emails
   of the account (`gh api user/emails`), GitHub being the default source. Confirm the exact `Name <email>`. For commits
   to show as verified, the email must match a verified email at the Git host.
5. Secrets encryption with a KMS (optional, skippable). The `sops-kms` skill covers SOPS with Google Cloud KMS
   (a project, billing and KMS rights) and with OpenBao transit (a reachable OpenBao and policy rights). Ask which one exists.
6. Hardware: one root key and two daily keys from the YubiKey 5 series, firmware 5.7.4 or later (read it with
   `ykman info`; the `ykman` tool itself needs 5.x), and three USB sticks (1: 8 GB or more for Tails; 2: LUKS for the
   backup; 3: FAT for the public key and these scripts).
7. How many USB ports are free. One is enough: Tails keeps its port. The encrypted backup is exported to memory first
   (`b4-backup.sh`) and then copied to each stick in turn (`b4-copy.sh`). With both sticks attached the flow is the
   same and only faster.
