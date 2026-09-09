# code-quality:measure regression tests

Runs as part of `nix flake check` (the `code-quality-tests` check, aarch64-darwin and
x86_64-linux only) — every required tool is provisioned hermetically, either from
nixpkgs directly or pinned in `../../../../nix/code-quality-tools.nix` for tools
nixpkgs doesn't package. No setup needed: `nix flake check`, or build just this one
with `nix build .#checks.<system>.code-quality-tests`.

Can also run directly with those tools on PATH some other way:

```bash
pip install crap4py pytest pytest-cov complexipy pyscn   # python side
cargo install cargo-crap cargo-iceberg4rust cargo-llvm-cov jscpd
cargo install --git https://github.com/mozilla/rust-code-analysis rust-code-analysis-cli

pytest tests/
```

Missing any tool → the whole module skips with a message naming exactly what's
absent, rather than failing.

`fixtures/` holds plain source, no git history — `test_measure.py` copies each
into a temp directory and synthesizes commits itself at run time, since a
tracked `.git` directory inside this repo would read as a submodule reference,
not real history. The exact commit counts in `test_measure.py`'s fixtures are
what the hotspot assertions are keyed to — change one, update the other.
