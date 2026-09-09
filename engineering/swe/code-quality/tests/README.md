# code-quality:measure regression tests

Not part of `nix flake check` — see `test_measure.py`'s own module docstring for
why (needs real Rust/Python toolchains the repo's devShell doesn't provision).

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
