# Rust — Code Quality Metrics

## Metrics tracked

| Metric   | Tracks                                                                                       | Tool                 |
| -------- | -------------------------------------------------------------------------------------------- | -------------------- |
| CRAP     | Per-function risk combining cyclomatic complexity with how untested it is                    | `cargo-crap`         |
| FileRisk | Private-implementation bloat behind a file's public surface — what per-function metrics miss | `cargo-iceberg4rust` |

Cyclomatic complexity and test coverage come free from `cargo-crap`'s own report (its
`CC` and coverage columns) — no separate tool needed for either.

### Formulas

```
CRAP(m)   = CC² × (1 − cov)³ + CC                                    -- >30 flagged
FileRisk  = (log2(1 + L) / 10) × (P + 0.5·ΣCᵢ + 0.5·D + 2.0·B)        -- default threshold 20
```

`CC` cyclomatic complexity, `cov` fraction covered. `L` effective lines, `P` private
functions, `Cᵢ` their complexity, `D`/`B` private data-only/behavioural helper structs.

## Tool choices, and why

**`cargo-crap` over `crap4rust`** — `crap4rust` hard-couples itself to one coverage
path (shells out to `cargo llvm-cov`, needs the `llvm-tools` rustup component).
`cargo-crap` just consumes an `--lcov` file, ships prebuilt binaries, and has more
CI-mature output (`--format sarif/github/pr-comment`, `--baseline`/`--fail-regression`).

**`cargo-iceberg4rust`** — pure static `syn`-AST analysis. No build or coverage step,
no extra toolchain component — the cheapest tool here, and it catches file-level mess
per-function checks can't.

## Ruled out

- **`crap4rust`** — see above.
- **`twin4rust`** — requires an external mirrored test file per source file and
  strips `#[cfg(test)]` blocks before checking. Incompatible with inline unit tests —
  would flag every such file as untested, permanently.
- **`stern4rust`** — a house-style linter, not an AI-code-trust signal. Different
  concern; adopt separately if wanted.

## Getting the tools

`cargo install cargo-crap cargo-iceberg4rust` works anywhere Rust does. Coverage
needs `cargo-llvm-cov` (`cargo install cargo-llvm-cov`) plus the `llvm-tools-preview`
toolchain component — `cargo-tarpaulin` skips that component but its ptrace-based
engine is Linux-only.

Nix is one way to provision these, not the only one — treat it as an example, not a
requirement: `cargo-crap` ships prebuilt release binaries (a plain `fetchurl`
derivation); `cargo-iceberg4rust` has none, so `rustPlatform.buildRustPackage` against
its crates.io source; `llvm-tools-preview` needs a toolchain built via
`fenix`/`rust-overlay` (plain `nixpkgs.rustc` doesn't ship it). Whatever the project
uses instead — asdf, system packages, a container image — `assets/run.sh` only cares
that the tools end up on `PATH`.

## Invocation

`assets/rust/run.sh <manifest-path>` does discovery (what's on `PATH`), fan-out (each
available metric, in parallel), and a summary. CRAP isn't fully independent the way
FileRisk is — it needs its own coverage pass first — but still runs as one parallel
branch. Pass a pre-generated lcov file as `crap.sh`'s second argument to skip
regenerating coverage (e.g. one a cached build already produced). Each metric script
is also independently runnable.

## Known limitation

Finding extraction reads `cargo-crap`/`cargo-iceberg4rust`'s human-readable tables,
not `--format json`/`--json`. `cargo-crap`'s JSON schema is documented and safe to
adopt; `cargo-iceberg4rust`'s real field names haven't been verified against actual
output, so switching would mean guessing a schema — revisit once that's checked.

Mutation testing, dependency-structure, and module-size metrics aren't covered yet —
tracked as a follow-up rather than guessed at here.
