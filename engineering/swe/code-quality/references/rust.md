# Rust — Code Quality Metrics

## Metrics tracked

| Metric               | Tracks                                                                                                                | Tool                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| CRAP                 | Per-function risk combining cyclomatic complexity with how untested it is                                             | `cargo-crap`                                     |
| FileRisk             | Private-implementation bloat behind a file's public surface — what per-function metrics miss                          | `cargo-iceberg4rust`                             |
| Cognitive Complexity | How hard a function actually reads to a human — penalizes nesting/breaks in linear flow, unlike cyclomatic complexity | `rust-code-analysis-cli`                         |
| Hotspots             | Complexity × how often a file is actually touched — flags complex code that's also actively changing                  | `rust-code-analysis-cli` + `git log` (see below) |
| Duplication %        | Percentage of near-duplicate code across the project                                                                  | `jscpd`                                          |
| IAD                  | Robert C. Martin's Instability/Abstractness/Distance-from-Main-Sequence, per crate                                    | `cargo-anatomy`                                  |
| MI                   | Maintainability Index per file (original / SEI / Visual Studio variants)                                              | `rust-code-analysis-cli`                         |
| Halstead             | Halstead volume/difficulty/effort/vocabulary/length/bugs per file                                                     | `rust-code-analysis-cli`                         |
| LOC                  | Lines-of-code family per file — SLOC/PLOC/LLOC/CLOC/BLANK (also answers "oversized module")                           | `rust-code-analysis-cli`                         |
| NOM                  | Functions + closures per file (the other half of "oversized module")                                                  | `rust-code-analysis-cli`                         |
| Mutation             | Test-suite strength — mutants the tests fail to catch (survivors), + a kill score. Opt-in (heavy)                     | `cargo-mutants`                                  |
| Dead code            | rustc dead_code/unused_\* lints (pub items are never flagged)                                                         | `cargo check --message-format=json`              |
| Unused deps          | Declared dependencies never referenced in source, per crate                                                           | `cargo-machete`                                  |
| Unsafe               | Textual `unsafe`-keyword count per file (crude — counts comments/strings too)                                         | `grep`                                           |
| API surface          | Count + list of a library crate's public items                                                                        | `cargo-public-api` (+ rustdoc)                   |
| Orphans              | Source files on disk never linked into the module tree                                                                | `cargo-modules`                                  |
| Fan-in/out           | Per-module inbound/outbound cross-module `uses` coupling                                                              | `cargo-modules`                                  |

IAD is computed at the **crate** level (each workspace crate is a Martin "package").
No verified tool computes it at the intra-crate **module** level for Rust — see Known
limitation below.

Cyclomatic complexity and test coverage come free from `cargo-crap`'s own report (its
`CC` and coverage columns) — no separate tool needed for either. **MI, Halstead, LOC and
NOM likewise come free from the same `rust-code-analysis-cli -m -O json` run that
Cognitive Complexity already uses** (shared in `assets/lang/rust/rca.sh`) — the tool
emitted them all along; the skill simply surfaces them now. MI's headline is
`mi_visual_studio` (0–100, higher better; `mi_sei` uses log2, diverging from the textbook
SEI formula, so treat it cautiously). For a file the tool can't compute a value on (e.g.
MI or Halstead difficulty on a file with no operands) it emits `null`, not NaN, so the
JSON stays valid.

### Formulas

```
CRAP(m)   = CC² × (1 − cov)³ + CC                                    -- >30 flagged
FileRisk  = (log2(1 + L) / 10) × (P + 0.5·ΣCᵢ + 0.5·D + 2.0·B)        -- default threshold 20
Hotspot   = touches × cognitive-complexity-sum, per file
I = Ce / (Ca + Ce)   A = traits / N   D = |A + I − 1| / √2   (per crate)
```

`Ca`/`Ce` afferent/efferent coupling (crates depending on this crate's types vs. this
crate depending on others'), `A` abstractness (fraction of a crate's `N` types that are
traits), `I` instability, `D` normalized distance from the main sequence. `cargo-anatomy`
also reports the un-normalized `D' = |A + I − 1|`, plus `N`, `R` (internal relations),
and `H = (R+1)/N` relational cohesion.

`CC` cyclomatic complexity, `cov` fraction covered. `L` effective lines, `P` private
functions, `Cᵢ` their complexity, `D`/`B` private data-only/behavioural helper structs.
Cognitive Complexity has no closed-form formula the way CRAP/FileRisk do — it's an
algorithm (nesting-weighted control-flow walk) defined in G. Ann Campbell's original
SonarSource whitepaper, not a short equation. `touches` comes from `git log`,
`cognitive-complexity-sum` from this same language's own tool above — see Tool
choices below for why Hotspots is a join rather than a dedicated tool.

## Tool choices, and why

**`cargo-crap` over `crap4rust`** — `crap4rust` hard-couples itself to one coverage
path (shells out to `cargo llvm-cov`, needs the `llvm-tools` rustup component).
`cargo-crap` just consumes an `--lcov` file, ships prebuilt binaries, and has more
CI-mature output (`--format sarif/github/pr-comment`, `--baseline`/`--fail-regression`).

**`cargo-iceberg4rust`** — pure static `syn`-AST analysis. No build or coverage step,
no extra toolchain component — the cheapest tool here, and it catches file-level mess
per-function checks can't.

**`cargo-anatomy`** (MIT) — the one tool found that computes Martin's full Ca/Ce/I/A/D
set for Rust, at the crate level, JSON by default. Same `syn`-AST + `cargo_metadata`
approach a from-scratch build would take, so adopting it avoids reimplementing name
resolution. Defines abstractness as traits/total-types — the natural Rust reading of
Martin's abstract-vs-concrete split. Two caveats: it's crate-level only (no intra-crate
module resolution), and it sees source as written, so **macro-generated types are
invisible unless `cargo expand` runs first**. By default only workspace members are
scored; set `CODE_QUALITY_IAD_EXTERNAL_SCOPE` to a cargo-anatomy scope selector (e.g.
`pkg-prefix:hopr`, comma-separated for several) to widen the graph to matching external
crates — needed when a project's members couple mainly to sibling crates published from
other workspaces, where the members-only view under-reports coupling. A scope matching
no external crate degrades to the members-only view rather than failing.

**`rust-code-analysis-cli`** (Mozilla, MPL-2.0) — the only real Cognitive Complexity
tool found for Rust; `clippy`'s own `cognitive_complexity` lint explicitly disclaims
itself in its source comments as a rough approximation, restriction-tier, warning-only
(no score export) — not suitable for a metrics pipeline. The crates.io release
(`0.0.25`, 2023-01-13) is stale relative to the project's actively-developed GitHub
`master`, so this is installed via `cargo install --git` rather than from crates.io
(see Getting the tools below) — the COGNITIVE metric itself already existed well
before that stale release, confirmed directly in source.

**`cargo-mutants`** (MIT) — mutation testing on the unmodified tree with a stable
toolchain, emitting machine-readable `mutants.out/outcomes.json`; the kill score is
`caught / (total_mutants − unviable)`, guarding the all-unviable case (it reports
`missed: 0` and exits 0 — "passes having tested nothing"). It exits nonzero when mutants
survive/time out, a finding rather than an error (like `cargo-iceberg4rust`'s exit 2), so
`mutation.sh` trusts a valid `outcomes.json` over the exit code. Because it rebuilds and
reruns the whole test suite once per mutant, it's an order of magnitude heavier than the
static metrics, so run.sh leaves it **out of the default `measure` sweep** unless
`CODE_QUALITY_ENABLE_MUTATION` is set; `mutation.sh` is also runnable directly. On a large
project bound it with `CODE_QUALITY_MUTATION_ARGS` (e.g. `--in-diff changes.diff`, `-j 4`).

**Structural metrics (dead code, unused deps, unsafe).** Dead code uses rustc's own
`dead_code`/`unused_*` lints via `cargo check --message-format=json` — no new tool, but
rustc never flags a `pub` item, so a genuinely-unused public API won't show (the module
`orphans` view, still an open follow-up, would catch those). Unused dependencies use
`cargo-machete` (MIT), a static source/manifest scan — no build or network; this version
has no JSON output so its text report is parsed (exit 1 = found unused, 0 = none). Unsafe
density is a plain word-boundary `grep` count per file, deliberately crude (it counts the
keyword in comments and strings too) and dependency-free; `cargo-geiger` would give
dependency-tree accounting but is flaky on complex workspaces, so it's left out.

**Module-graph metrics (API surface, orphans, fan-in/out).** `cargo-public-api` needs
rustdoc JSON, an unstable format normally requiring nightly; `api.sh` unlocks it on the
stable toolchain with `RUSTC_BOOTSTRAP=1` (the standard CI escape hatch) instead of
depending on a nightly install — library crates only, and auto-trait/blanket impls (which
`--simplified` doesn't fully drop) are filtered so the count is the crate's own declared
public items. `cargo-modules` (rust-analyzer-based, stable toolchain) provides both
`orphans` (files never linked with `mod`, which rustc can't see) and `dependencies` (a
Graphviz DOT graph, no JSON — color disabled via `NO_COLOR`); `fanio.sh` rolls its
item-level `uses` edges up to owning modules for per-module fan-in/out.

**`jscpd`** (MIT) — one tool covers both Rust and Python duplication detection with a
single consistent percentage, rather than a separate per-language tool. Confirmed via
its own `FORMATS.md` to support `.rs` as a first-class format, not just JS/TS despite
the name.

**Hotspots has no dedicated tool.** `assets/lang/shared/hotspots.sh` (shared with
Python) explains why and documents the join; `code-maat`, the closest thing to a
reference implementation, was ruled out as a dependency (JVM/Clojure, slow-moving)
in favor of the plain `git log` churn count it uses joined against
`rust-code-analysis-cli`'s own per-file complexity sum — zero new tool needed beyond
what Cognitive Complexity already requires.

## Ruled out

- **`crap4rust`** — see above.
- **`twin4rust`** — requires an external mirrored test file per source file and
  strips `#[cfg(test)]` blocks before checking. Incompatible with inline unit tests —
  would flag every such file as untested, permanently.
- **`stern4rust`** — a house-style linter, not an AI-code-trust signal. Different
  concern; adopt separately if wanted.

## Getting the tools

`cargo install cargo-crap cargo-iceberg4rust cargo-anatomy cargo-mutants cargo-machete cargo-public-api cargo-modules jscpd`
works anywhere Rust does (dead code and unsafe need only `cargo` and `grep`; API surface
additionally shells `RUSTC_BOOTSTRAP=1 cargo rustdoc` on stable). Coverage
needs `cargo-llvm-cov` (`cargo install cargo-llvm-cov`) plus the `llvm-tools-preview`
toolchain component — `cargo-tarpaulin` skips that component but its ptrace-based
engine is Linux-only. Cognitive Complexity and Hotspots both need
`cargo install --git https://github.com/mozilla/rust-code-analysis rust-code-analysis-cli`
(from git HEAD, not crates.io — see above); Hotspots additionally needs `jq` (any
package manager) to join its churn/complexity data, and a real, non-shallow git
working copy for the target project (see Known limitation below).

## Invocation

`assets/run.sh <manifest-path>` (the generic entrypoint — see SKILL.md; it also
accepts other languages' manifests alongside this one for multi-language projects)
does discovery (what's on `PATH`), fan-out (each available metric, in parallel), and
prints one combined JSON object on stdout — nothing else. CRAP isn't fully
independent the way FileRisk is — it needs its own coverage pass first — but still
runs as one parallel branch. Pass a pre-generated lcov file as
`assets/lang/rust/crap.sh`'s second argument to skip regenerating coverage (e.g. one
a cached build already produced). Each metric script under `assets/lang/rust/` is
also independently runnable, and each one's own stdout is that same JSON shape on
its own — `assets/run.sh` just collects them. Want a table instead of JSON?
`assets/report.sh` runs `run.sh` and formats its output.

## Known limitation

**`cargo-crap --format json` and `cargo-iceberg4rust --json` are both real and
verified** — confirmed directly against live output, not assumed from `--help` text.
`cargo-crap`'s schema: `{entries: [{file, function, line, cyclomatic, coverage,
crap, uncovered}], diagnostics}`. `cargo-iceberg4rust`'s: `{threshold, scored_files,
visible_files, total_risk, files: [{relative_file, risk_score,
private_function_count, private_complexity_sum, ...}]}`.

**`cargo-iceberg4rust` exits 2, not 0, whenever anything crosses `--threshold`** — a
CI-gate convention, not an error. `filerisk.sh` explicitly captures the exit code and
treats 0 and 2 as equally valid rather than trusting `set -e` — a naive invocation
silently produced empty output on every real finding until this was caught by
testing against a fixture deliberately built to trigger one, not just a "no findings"
fixture.

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

**Instability/Abstractness/Distance (Robert C. Martin, _Agile Software Development:
Principles, Patterns, and Practices_, 2002) — crate level only.** `cargo-anatomy`
computes the full Ca/Ce/I/A/D set per crate (the IAD metric above). What it does _not_
do is intra-crate, **module**-level coupling, and no verified tool does: `cargo-modules`
is a dependency-graph _visualizer_ (Graphviz/tree output only, no numeric coupling), and
`cargo-coupling` sounds related but implements a different framework entirely (Vlad
Khononov's Integration Strength/Distance/Volatility model, not Martin's formulas) —
checked directly against its own README, not assumed from its name. Accurate
module-level Ca/Ce would need `rust-analyzer`'s own name resolution; that stays an open
gap here rather than an invented approximation.

**Hotspots requires a real git working copy.** Churn counting needs `.git` history —
a bare checkout, tarball, or shallow clone (`git clone --depth`) has none or an
incomplete one; `hotspots.sh` checks for both and reports a clear skip rather than a
misleadingly low (or zero) score.

Module-size (LOC/NOM), mutation testing, public API surface, orphans, and module-level
fan-in/out are all covered now. The remaining known gap is intra-crate module-level
Martin coupling (I/A/D) — see the note above; no verified tool provides it.
