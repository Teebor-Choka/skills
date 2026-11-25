# Sources

Re-check time-sensitive details here before relying on them.

- `ykman` 5.9.1 `--help` for `piv keys import`, `piv certificates import`, `piv access change-pin`,
  `piv access change-puk`, `piv access change-management-key`.
- Yubico genuineness check: https://www.yubico.com/genuine/
- PIV certificate slots: https://developers.yubico.com/PIV/Introduction/Certificate_slots.html
- `ykman` PIV commands: https://docs.yubico.com/software/yubikey/tools/ykman/PIV_Commands.html
- Tails installation and verification: https://tails.net
- Tails Persistent Storage: https://tails.net/doc/persistent_storage/configure/index.en.html
- X.509 name constraints and path length: RFC 5280, sections 4.2.1.9 and 4.2.1.10:
  https://www.rfc-editor.org/rfc/rfc5280
- Tails memory erasure at shutdown (cited from the Tails design pages, not re-read for this skill):
  https://tails.net/contribute/design/memory_erasure/
- The sibling `yubikey` skill: firmware floor, genuineness checks and Tails stick preparation.
