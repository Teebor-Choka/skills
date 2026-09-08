# Rust — Code Quality Metrics

## Metrics tracked

| Metric               | Tracks                                                                                                                | Tool                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| CRAP                 | Per-function risk combining cyclomatic complexity with how untested it is                                             | `cargo-crap`                                     |
| FileRisk             | Private-implementation bloat behind a file's public surface — what per-function metrics miss                          | `cargo-iceberg4rust`                             |
| Cognitive Complexity | How hard a function actually reads to a human — penalizes nesting/breaks in linear flow, unlike cyclomatic complexity | `rust-code-analysis-cli`                         |
| Hotspots             | Complexity × how often a file is actually touched — flags complex code that's also actively changing                  | `rust-code-analysis-cli` + `git log` (see below) |
| Duplication %        | Percentage of near-duplicate code across the project                                                                  | `jscpd`                                          |

No verified tool computes Robert C. Martin's Instability/Abstractness/Distance-from-
Main-Sequence metrics for Rust — see Known limitation below.

Cyclomatic complexity and test coverage come free from `cargo-crap`'s own report (its
`CC` and coverage columns) — no separate tool needed for either.

### Formulas

```
CRAP(m)   = CC² × (1 − cov)³ + CC                                    -- >30 flagged
FileRisk  = (log2(1 + L) / 10) × (P + 0.5·ΣCᵢ + 0.5·D + 2.0·B)        -- default threshold 20
Hotspot   = touches × cognitive-complexity-sum, per file
```

`CC` cyclomatic complexity, `cov` fraction covered. `L` effective lines, `P` private
functions, `Cᵢ` their complexity, `D`/`B` private data-only/behavioural helper structs.
Cognitive Complexity has no closed-form formula the way CRAP/FileRisk do — it's an
algorithm (nesting-weighted control-flow walk) defined in G. Ann Campbell's original
SonarSource whitepaper, not a short equation. Hotspots isn't from a single tool: it's
the same manual join Adam Tornhill's own `code-maat` documents in its README (join a
churn count against a separately-computed complexity source by hand) — `touches` comes
from `git log`, `cognitive-complexity-sum` from this same language's own tool above.

## Tool choices, and why

**`cargo-crap` over `crap4rust`** — `crap4rust` hard-couples itself to one coverage
path (shells out to `cargo llvm-cov`, needs the `llvm-tools` rustup component).
`cargo-crap` just consumes an `--lcov` file, ships prebuilt binaries, and has more
CI-mature output (`--format sarif/github/pr-comment`, `--baseline`/`--fail-regression`).

**`cargo-iceberg4rust`** — pure static `syn`-AST analysis. No build or coverage step,
no extra toolchain component — the cheapest tool here, and it catches file-level mess
per-function checks can't.

**`rust-code-analysis-cli`** (Mozilla, MPL-2.0) — the only real Cognitive Complexity
tool found for Rust; `clippy`'s own `cognitive_complexity` lint explicitly disclaims
itself in its source comments as a rough approximation, restriction-tier, warning-only
(no score export) — not suitable for a metrics pipeline. The crates.io release
(`0.0.25`, 2023-01-13) is stale relative to the project's actively-developed GitHub
`master`, so this is installed via `cargo install --git` rather than from crates.io
(see Getting the tools below) — the COGNITIVE metric itself already existed well
before that stale release, confirmed directly in source.

**`jscpd`** (MIT) — one tool covers both Rust and Python duplication detection with a
single consistent percentage, rather than a separate per-language tool. Confirmed via
its own `FORMATS.md` to support `.rs` as a first-class format, not just JS/TS despite
the name.

**Hotspots has no dedicated tool** — Tornhill's own reference implementation,
`code-maat`, only measures churn itself; its README documents joining that against a
separately-computed complexity source by hand, the same join done here. `code-maat`
was ruled out as a dependency (JVM/Clojure, slow-moving) in favor of a plain `git log`
churn count joined against `rust-code-analysis-cli`'s own per-file complexity sum —
zero new tool needed beyond what Cognitive Complexity already requires.

## Ruled out

- **`crap4rust`** — see above.
- **`twin4rust`** — requires an external mirrored test file per source file and
  strips `#[cfg(test)]` blocks before checking. Incompatible with inline unit tests —
  would flag every such file as untested, permanently.
- **`stern4rust`** — a house-style linter, not an AI-code-trust signal. Different
  concern; adopt separately if wanted.

## Getting the tools

`cargo install cargo-crap cargo-iceberg4rust jscpd` works anywhere Rust does. Coverage
needs `cargo-llvm-cov` (`cargo install cargo-llvm-cov`) plus the `llvm-tools-preview`
toolchain component — `cargo-tarpaulin` skips that component but its ptrace-based
engine is Linux-only. Cognitive Complexity and Hotspots both need
`cargo install --git https://github.com/mozilla/rust-code-analysis rust-code-analysis-cli`
(from git HEAD, not crates.io — see above); Hotspots additionally needs `jq` (any
package manager) to join its churn/complexity data, and a real, non-shallow git
working copy for the target project (see Known limitation below).

Nix is one way to provision these, not the only one — treat it as an example, not a
requirement: `cargo-crap` ships prebuilt release binaries (a plain `fetchurl`
derivation); `cargo-iceberg4rust` has none, so `rustPlatform.buildRustPackage` against
its crates.io source; `llvm-tools-preview` needs a toolchain built via
`fenix`/`rust-overlay` (plain `nixpkgs.rustc` doesn't ship it). Whatever the project
uses instead — asdf, system packages, a container image — `assets/run.sh` only cares
that the tools end up on `PATH`.

## Invocation

`assets/run.sh <manifest-path>` (the generic entrypoint — see SKILL.md; it also
accepts other languages' manifests alongside this one for multi-language projects)
does discovery (what's on `PATH`), fan-out (each available metric, in parallel), and
a summary. CRAP isn't fully independent the way FileRisk is — it needs its own
coverage pass first — but still runs as one parallel branch. Pass a pre-generated
lcov file as `assets/lang/rust/crap.sh`'s second argument to skip regenerating
coverage (e.g. one a cached build already produced). Each metric script under
`assets/lang/rust/` is also independently runnable.

## Known limitation

Finding extraction reads `cargo-crap`/`cargo-iceberg4rust`'s human-readable tables,
not `--format json`/`--json`. `cargo-crap`'s JSON schema is documented and safe to
adopt; `cargo-iceberg4rust`'s real field names haven't been verified against actual
output, so switching would mean guessing a schema — revisit once that's checked.

**FileRisk in a Cargo workspace.** `cargo-iceberg4rust` resolves `--manifest-path` via
`cargo_metadata`, which reports the _whole_ workspace's package list even when pointed
at one member's own manifest — so it demands `--package <name>` whenever the
workspace has more than one member, regardless of which manifest was passed. Verified
against a real two-package workspace: pointing at a member's own `Cargo.toml`
resolves cleanly (`filerisk.sh` reads that manifest's own `[package]` name and passes
`--package` automatically — not a guess, since a manifest naming itself is
unambiguous); pointing at the workspace root's `Cargo.toml` still fails, since a
workspace-root-only manifest has no `[package]` section to derive a name from at all,
and there is genuinely no single member to disambiguate to without one. `cargo-crap`
has no such issue — `--path` is a plain filesystem walk, so both pointings work.

**No Instability/Abstractness/Distance-from-Main-Sequence (Robert C. Martin,
_Agile Software Development: Principles, Patterns, and Practices_, 2002).**
`cargo-modules` is a dependency-graph _visualizer_ (Graphviz/tree output only, no
numeric coupling); `cargo-coupling` sounds related but implements a different
framework entirely (Vlad Khononov's Integration Strength/Distance/Volatility model,
not Martin's Ca/Ce/I/A/D formulas) — checked directly against its own README rather
than assumed from its name. No tool computing Martin's actual formulas was found for
Rust. Python has one (`pyscn` — see `references/python.md`); this stays an open gap
here rather than an invented approximation.

**Hotspots requires a real git working copy.** Churn counting needs `.git` history —
a bare checkout, tarball, or shallow clone (`git clone --depth`) has none or an
incomplete one; `hotspots.sh` checks for both and reports a clear skip rather than a
misleadingly low (or zero) score.

Mutation testing and module-size metrics aren't covered yet — tracked as a follow-up
rather than guessed at here.
