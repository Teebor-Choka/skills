# Nix gotchas

Errors seen repeatedly when editing home-manager and flake config.

- **Define an attribute once.** `home.activation.x = ...;` and `home.activation = { x = ...; };` in
  one file fail with `attribute 'home.activation' already defined`. Use the dotted form or the
  attrset form per path, not both.
- **Wrap activation entries as DAG data.** A `home.activation.<name>` value is a DAG entry, not a
  bare string: `lib.hm.dag.entryAfter [ "writeBoundary" ] ''...''`.
- **Escape `${` in indented strings.** In `'' ... ''`, shell `${VAR}` is Nix interpolation. Write
  `''${VAR}` for a literal shell expansion.
- **New files are invisible to a flake until tracked.** `git add -N <explicit paths>`, never
  `git add -N .`.
- **GNU and BSD `stat` differ.** `stat -c %s f` is GNU; `stat -f %z f` is BSD. `stat: illegal
option` means a GNU flag ran on macOS. Branch on `uname` or use a portable form.
