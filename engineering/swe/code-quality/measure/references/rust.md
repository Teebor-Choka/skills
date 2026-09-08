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

**`cargo-crap` over `crap4rust`** — `crap4rust` couples itself to one coverage
path: it shells out to `cargo llvm-cov` itself and requires the `llvm-tools`
rustup component. `cargo-crap` just consumes an `--lcov` file, ships prebuilt
binaries (including `aarch64-apple-darwin` — packaging is a plain `fetchurl`
derivation, no `cargoHash` to maintain), and has more CI-mature output
(`--format sarif/github/pr-comment`, `--baseline`/`--fail-regression`).

**`cargo-iceberg4rust`** — pure static `syn`-AST analysis. No build step, no
coverage input, no `llvm-tools` dependency — the cheapest tool here. Complements
CRAP by catching file-level mess per-function complexity checks can't see.

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

`cargo-tarpaulin` avoids the `llvm-tools-preview` problem, but its ptrace-based
engine is Linux-only, not viable on macOS — so on a mixed-platform team,
`llvm-tools-preview` isn't avoidable.

## Nix integration order

1. Add a Rust toolchain overlay (`fenix` or `rust-overlay`) as a new flake input,
   configured with the `llvm-tools-preview` extension.
2. Add `pkgs.cargo-llvm-cov` to the devShell's `nativeBuildInputs`.
3. Package `cargo-crap` as a `fetchurl` derivation pulling the release tarball for
   the target platform(s).
4. Package `cargo-iceberg4rust` via `rustPlatform.buildRustPackage` against its
   crates.io source.

## Invocation / run order

Run `../assets/run.sh <path-to-Cargo.toml's-dir>` — it dispatches to
`assets/rust/run.sh`, which does three things, all deterministic (no LLM
involved):

1. **Discovery** — checks which metrics have their required tools on `PATH`
   and prints a minireport before anything runs, e.g.:
   ```
   == code-quality:measure discovery (rust) ==
     [available] filerisk
     [missing]   crap (needs: cargo-llvm-cov cargo-crap) -- see the skill's references/rust.md
   ```
2. **Fan-out** — each _available_ metric runs independently and in parallel:
   `assets/rust/filerisk.sh` and `assets/rust/crap.sh`. CRAP isn't fully
   independent like FileRisk — it needs a coverage report first, so
   `crap.sh` runs `cargo llvm-cov` then `cargo crap` sequentially inside
   itself. That two-tool pipeline is still one parallel branch alongside
   FileRisk; the sequencing is an inherent tool constraint, not a design
   choice.
3. **Summary** — every branch's report is printed together, labeled by
   metric.

Each metric script is also directly runnable on its own — useful for a human
or CI that only wants one metric:

```sh
# FileRisk alone — no prerequisites beyond the tool itself.
assets/rust/filerisk.sh Cargo.toml

# CRAP alone — runs its own coverage pass first.
assets/rust/crap.sh Cargo.toml

# Gate on CRAP specifically in CI, with SARIF/GitHub annotation output
# instead of the plain-text report the script prints:
cargo crap --manifest-path Cargo.toml --workspace --lcov lcov.info --fail-above --format sarif
```

## Known limitation: finding extraction reads tables, not JSON

The verify workflows (`assets/measure.workflow.js`, `opencode/`) extract findings by
having an LLM read `cargo-crap`/`cargo-iceberg4rust`'s plain human-readable output
(the ✗/▲/✓-marked table, the "Offender detail" section) rather than requesting
`--format json`/`--json`. This is deliberate for now, not an oversight: `cargo-crap`'s
JSON schema is fully documented (`schemas/report-v1.json`) and safe to switch to, but
`cargo-iceberg4rust`'s exact JSON field names haven't been verified here — inventing a
parser against an unconfirmed schema would repeat the exact mistake this whole skill
exists to catch (plausible-looking code built on an unverified claim). The table-based
approach works today per its own tools' output conventions; revisit once
`cargo-iceberg4rust --json`'s real shape has been checked against actual output.

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
