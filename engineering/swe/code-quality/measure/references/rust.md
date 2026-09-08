# Rust — Code Quality Metrics

## Metrics tracked

| Metric                | Tracks                                                                                                                                                                                                                                       | Tool                                                          |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| CRAP score            | Per-function risk combining cyclomatic complexity with how untested it is                                                                                                                                                                    | `cargo-crap`                                                  |
| Test coverage         | % of lines/regions executed by tests — the input CRAP needs, also worth reporting alone                                                                                                                                                      | `cargo-llvm-cov`                                              |
| Cyclomatic complexity | Independent paths through a function                                                                                                                                                                                                         | Comes free from `cargo-crap`'s `CC` column — no separate tool |
| FileRisk              | Private-implementation bloat hiding behind a file's public surface — what per-function metrics can't see (27 tiny private helpers, one function carrying half a file's complexity, a "decoder" and "encoder" sharing nothing but a filename) | `cargo-iceberg4rust`                                          |

### Formulas

```
CRAP(m)   = CC² × (1 − cov)³ + CC                                    -- >30 flagged
FileRisk  = (log2(1 + L) / 10) × (P + 0.5·ΣCᵢ + 0.5·D + 2.0·B)        -- default threshold 20
```

`CC` cyclomatic complexity, `cov` fraction covered. `L` effective lines, `P` private
functions, `Cᵢ` their complexity, `D`/`B` private data-only/behavioural helper structs.

## Tool choices, and why

**`cargo-crap` over `crap4rust`** — `crap4rust` shells out to `cargo llvm-cov` itself
and hard-requires the `llvm-tools` rustup component to do it automatically, coupling
the CRAP scorer to one specific coverage-generation path. `cargo-crap` only consumes
an `--lcov` file — it doesn't care how it was produced — and ships prebuilt release
binaries (including `aarch64-apple-darwin`), so it can be packaged as a plain
`fetchurl` derivation with no Rust compilation in the build sandbox. `crap4rust` has
no prebuilt binaries; packaging it means `buildRustPackage` + a `cargoHash` to
maintain. `cargo-crap` is also the more CI-mature tool: `--format sarif/github/pr-comment`,
JSON-schema-versioned output, `--baseline`/`--fail-regression` gating.

**`cargo-iceberg4rust`** — pure static `syn`-AST analysis. No build step, no
coverage input, no `llvm-tools` dependency at all — the cheapest and least
prerequisite-laden of everything here. Complements CRAP by catching mess at the
file level that per-function complexity checks structurally cannot see.

## Ruled out

- **`crap4rust`** — see above; coverage-generation coupling makes it the worse fit
  for a reproducible nix devshell.
- **`twin4rust`** — requires an external mirrored test file per source file
  (`src/foo.rs` → `tests/foo_tests.rs`) and explicitly strips out
  `#[cfg(test)]` blocks before evaluating whether a file needs one. Incompatible
  with the idiomatic Rust convention of inline unit tests in the same file — it
  would flag every such file as untested, permanently.
- **`stern4rust`** — a house-style linter (mandated file headers, import
  qualification, arrange-act-assert test shape, directory file-count limits). Real,
  and configurable via `skip`/baseline/per-package `stern4rust.toml`, but a
  different concern: convention consistency, not an AI-code-trust signal. Adopt
  separately if wanted; it isn't part of this chain.

## Prerequisites

| Requirement                                                              | Needed for          | Why                                                                                                                                                                                |
| ------------------------------------------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rust toolchain via `fenix` or `rust-overlay` (not plain `nixpkgs.rustc`) | coverage → CRAP     | Confirmed from nixpkgs' own `cargo-llvm-cov` package description: it needs the `llvm-tools-preview` component, which plain nixpkgs rustc does not ship.                            |
| `llvm-tools-preview` component on that toolchain                         | coverage → CRAP     | Same reason.                                                                                                                                                                       |
| `pkgs.cargo-llvm-cov` (in nixpkgs)                                       | coverage generation | Produces the `.lcov` file `cargo-crap` consumes.                                                                                                                                   |
| `cargo-crap` binary                                                      | CRAP score          | No nixpkgs package. Prebuilt release binaries exist for `aarch64-apple-darwin`/`x86_64-apple-darwin`/Linux — package via `fetchurl`. Building from source needs Rust stable ≥1.88. |
| `cargo-iceberg4rust` binary                                              | FileRisk score      | No nixpkgs package, no prebuilt binaries — `rustPlatform.buildRustPackage` from the crates.io source with a pinned `cargoHash`.                                                    |

`cargo-tarpaulin` is in nixpkgs and avoids the `llvm-tools-preview` problem, but its
ptrace-based coverage engine is Linux-only — not viable on macOS. On a mixed-platform
team, `cargo-llvm-cov` is the one coverage path that works everywhere, so the
`llvm-tools-preview` prerequisite above is not avoidable in general.

## Nix integration order

1. Add a Rust toolchain overlay (`fenix` or `rust-overlay`) as a new flake input,
   configured with the `llvm-tools-preview` extension.
2. Add `pkgs.cargo-llvm-cov` to the devShell's `nativeBuildInputs`.
3. Package `cargo-crap` as a `fetchurl` derivation pulling the release tarball for
   the target platform(s).
4. Package `cargo-iceberg4rust` via `rustPlatform.buildRustPackage` against its
   crates.io source.

## Invocation / run order

Run `../assets/run.sh <path-to-Cargo.toml's-dir>` — it dispatches here and runs the
chain below in order. It's plain shell, not Claude-specific: a human or CI can call
it the same way. Cheapest and fewest-prerequisites first:

```sh
# 1. No prerequisites — static analysis only, fails fast on structural rot.
cargo iceberg4rust --manifest-path Cargo.toml --workspace

# 2. Generate coverage once.
cargo llvm-cov --manifest-path Cargo.toml --workspace --lcov --output-path lcov.info

# 3. Gate on CRAP. Use --format sarif/github for CI code-scanning/annotations
#    instead of a plain pass/fail — the script prints the plain-text report;
#    call cargo-crap directly for other output formats.
cargo crap --manifest-path Cargo.toml --workspace --lcov lcov.info --fail-above
```

## Open — not yet verified to the same standard as the above

Named by the wider "what metrics do senior engineers use for AI agent code" research
this reference is drawn from, but not yet given the same nix-devshell diligence pass:

- **Mutation testing** — `cargo-mutants` is the likely candidate (tests whether
  the test suite actually catches injected mutations, catching high-coverage/weak-assertion
  agent-written tests). Nix packaging and devshell fit unverified.
- **Dependency structure** (stability/abstractness) — no concrete Rust tool
  identified.
- **Module size** — no dedicated tool; a plain line-count threshold would suffice,
  this isn't really a "metric" in the same sense as the others.

Do not wire in a guessed tool for these — extend this reference once each gets the
same verification pass CRAP and FileRisk got.
