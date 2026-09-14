# code-quality — Roadmap: fully-stocked Rust metrics, then generalize

Plan for extending the `measure` workflow into a fully-stocked metrics analyzer.
Grounded in a five-track tool survey (2026-09-13); every adopted tool below was
verified live (crates.io version, license, JSON output) on that date.

## Locked decisions

- **Rust-first depth.** Stock Rust completely before generalizing. The universal
  multi-language engine is deferred (Phase 2), decision recorded but not started.
- **Stock metrics first.** The risk-boundary scoring layer ("don't touch / safe to
  automate") is deferred (Phase 3) — it's the seed's ultimate purpose but out of scope
  until the metrics feeding it exist.
- **Adopt, don't build**, wherever a maintained, JSON-emitting tool exists.

## Corrections to `references/rust.md` (now stale)

The survey overturned three claims the reference currently makes:

1. **Coupling exists.** "No verified tool computes Martin's Instability/Abstractness/
   Distance for Rust" is outdated — [`cargo-anatomy`](https://github.com/cutsea110/cargo-anatomy)
   (MIT, JSON default, actively maintained) computes the full Ca/Ce/I/A/D set at
   **crate level**. The genuine remaining gap is _intra-crate module-level_ coupling
   (no tool; would need rust-analyzer internals). Keep the cargo-modules and
   cargo-coupling notes — both re-verified accurate.
2. **MI + Halstead are already free.** `rust-code-analysis-cli` (already installed for
   cognitive complexity) also emits Maintainability Index (3 variants) and the full
   Halstead suite — the skill just never surfaced them. Verified against master source.
3. **Mutation + module-size are no longer "follow-up."** Both are solvable now
   (`cargo-mutants`; LOC/NOM free from rust-code-analysis + `cargo-machete` etc.).

Apply these edits as part of Phase 0/1, not as a separate pass.

## Phase 0 — Verify & harden (no new tools)

1. **Confirm the baseline works.** Run `tests/test_measure.py` against the Rust +
   Python fixtures; confirm every currently-claimed metric still runs.
2. **Confirm tool availability** on PATH (the `discovery` block of `run.sh` output).
3. **Surface what rust-code-analysis already computes.** Switch the cognitive-metric
   invocation to `rust-code-analysis-cli -m -O json -p <path>` and parse the `mi`,
   `halstead`, `loc` (SLOC/PLOC/LLOC/CLOC/BLANK), and `nom` objects already present in
   its output — new metric rows `rust:mi`, `rust:halstead`, `rust:loc`, `rust:nom` from
   a tool already installed.
   - Headline MI = `mi_visual_studio` (bounded 0–100, maps to standard thresholds).
     Treat `mi_sei` cautiously (it uses log2, diverging from the textbook SEI formula).
   - **Guardrail:** sanitize `NaN`/`±inf` (trivial or operand-free spaces produce them;
     the tool has no internal guard) before aggregating or thresholding.

**Acceptance:** `run.sh` JSON gains `rust:mi`, `rust:halstead`, `rust:loc`, `rust:nom`;
no `NaN`/`inf` reaches output; existing tests stay green; `rust.md` corrections landed.

## Phase 1 — Fully stock Rust (fill the four gaps)

Each new metric follows the existing pattern: a script under `assets/lang/rust/`,
independently runnable, stdout = the same per-metric JSON shape `run.sh` collects.

### 1.1 Coupling — `assets/lang/rust/iad.sh` ✅ landed

Implemented as the `rust:iad` metric (named to match the existing `python:iad`
sibling, not `coupling`). `cargo-anatomy` 0.7.7 is pinned in
`nix/code-quality-tools.nix` and wired into the `code-quality-tests` check;
`tests/fixtures/rust-iad-sample` is a two-crate workspace exercising a real Ca/Ce
relationship. As-built notes:

- Tool: `cargo install cargo-anatomy`; run at workspace root, JSON is default.
- Emit per crate: `Ca`, `Ce`, `I`, `A` (= traits/total types), `D` (normalized) and
  `D'` (= `|A+I−1|`). Flag high-D crates (off the main sequence).
- Caveats to document: **crate-level only**; **macro-blind** — gate a `cargo expand`
  pre-pass for macro-heavy crates; pin the version and snapshot-test the JSON shape
  (young 0.x, schema may shift).

### 1.2 Mutation testing — `assets/lang/rust/mutation.sh`

- Tool: `cargo install --locked cargo-mutants`.
- Invocation (bounded — this is a checkpoint tool, not inner-loop):
  `cargo mutants --in-diff <diff> -j <n> --timeout <s>`; full-tree run as the slow
  alternative. Parse `mutants.out/outcomes.json`.
- Score: `mutation_score = caught / (total_mutants - unviable)`.
  **Guardrail:** require `(total_mutants - unviable) > 0` first — an all-unviable run
  reports `missed: 0` and exits 0 ("passes having tested nothing").
- Per-file/function breakdown from each mutant's `scenario`. Pin the version (on-disk
  schema is explicitly allowed to change).

### 1.3 Structural bundle — `assets/lang/rust/structure.sh`

Prioritized; ship top-down, each is independent:

- **Oversized modules/files (free):** threshold `SLOC`/`PLOC` per file and `NOM` per
  file from the Phase-0 rust-code-analysis output — no new tool.
- **Unused dependencies:** `cargo-machete --json` (fast, stable, MIT). Optional deeper
  CI gate: `cargo-udeps --output json` (nightly, full build).
- **Dead code:** `cargo check --message-format=json`, filter diagnostics
  `dead_code`/`unused_*`. Complement with `cargo modules orphans` (files never linked
  into the module tree — catches what `dead_code` misses behind a `pub` surface).
- **Unsafe density (build, trivial):** `rg`/`syn` count of `unsafe` per KLOC over
  first-party crates. `cargo-geiger --output-format Json` only when dependency-tree
  unsafe accounting is wanted (flaky on complex workspaces — budget for it).
- **Public API surface (optional):** `cargo-public-api --output json` (nightly, library
  crates only).
- **Fan-in/out (last, highest effort):** parse `cargo modules dependencies` DOT, roll
  item-level `Uses` edges up to owning modules. No JSON — DOT parse required.

**Acceptance (Phase 1):** `run.sh` emits `rust:coupling`, `rust:mutation`, and the
structural rows; each script is independently runnable and returns valid JSON on both a
"findings" and a "no findings" fixture; each new metric has a fixture that actually
triggers a finding (mirroring the FileRisk exit-code lesson in `rust.md`).

## Phase 2 — Generalize to arbitrary languages (DEFERRED; decision recorded)

Do not start until a concrete non-Rust need appears. When triggered:

- **Do not** adopt `rust-code-analysis` as the universal engine — only ~7 mainstream
  languages, uneven per-language metric coverage, no release since Jan 2023.
- **Recommended:** fork/vendor [`arborist-metrics`](https://github.com/StrangeDaysTech/arborist-metrics)
  (Rust + tree-sitter, cognitive/cyclomatic/SLOC with one consistent definition across
  languages, MIT/Apache; per-language onboarding ≈ a `LanguageProfile` + grammar +
  fixtures). Go equivalent: `codemetrics`.
- **Recorded tension:** the tree-sitter engine yields _only_ cognitive/cyclomatic/SLOC —
  **no Halstead, MI, or coupling**. So a layered model (rust-code-analysis deep for its
  languages + tree-sitter thin tier for the long tail) trades cross-language metric
  comparability for depth; a single tree-sitter engine trades depth for comparability.
  Resolve this at trigger time against the actual second language's needs.

## Phase 3 — Risk-boundary scoring layer (DEFERRED)

The metrics seed's actual purpose: synthesize CRAP + mutation score + coupling + MI into
a per-file/function **"don't touch / safe to automate"** verdict. Distinct from today's
pure-reporter design — a new synthesis step over `measure`'s JSON, not a new tool. Out
of scope until Phases 0–1 land.

## Adopted-tool reference (verified 2026-09-13)

| Metric                    | Tool                          | License    | JSON                    | Note                                   |
| ------------------------- | ----------------------------- | ---------- | ----------------------- | -------------------------------------- |
| MI + Halstead + LOC + NOM | rust-code-analysis (git HEAD) | MPL-2.0    | yes                     | already installed                      |
| Coupling Ca/Ce/I/A/D      | cargo-anatomy                 | MIT        | yes (default)           | crate-level; macro-blind               |
| Mutation score            | cargo-mutants                 | MIT        | `outcomes.json`         | bound via `--in-diff`/`-j`/`--timeout` |
| Unused deps               | cargo-machete                 | MIT        | `--json`                | udeps = nightly deep gate              |
| Dead code                 | rustc via `cargo check`       | —          | `--message-format=json` | + `cargo modules orphans`              |
| Public API surface        | cargo-public-api              | MIT        | `--output json`         | nightly, libs only                     |
| Unsafe (dep tree)         | cargo-geiger                  | MIT/Apache | `--output-format Json`  | flaky; first-party via rg/syn          |
| Fan-in/out                | cargo-modules                 | MPL-2.0    | DOT only                | roll up to modules                     |

## Re-runnable validation checklist

```
# Phase 0
python -m pytest tests/test_measure.py -q
sh assets/run.sh tests/fixtures/rust-sample/Cargo.toml | jq '.results | keys'
#   expect keys to include: rust:mi, rust:halstead, rust:loc, rust:nom (+ existing)
sh assets/run.sh tests/fixtures/rust-sample/Cargo.toml | jq '.. | .mi? // empty' \
  | grep -Ei 'nan|inf' && echo "FAIL: unsanitized" || echo "OK: sanitized"

# Phase 1 (once scripts land)
sh assets/lang/rust/coupling.sh tests/fixtures/rust-sample/Cargo.toml | jq '.rows[0] | keys'
#   expect: Ca, Ce, I, A, D, D'
sh assets/lang/rust/mutation.sh tests/fixtures/rust-sample/Cargo.toml | jq '.summary'
#   expect caught/total/unviable present; score only when (total-unviable)>0
```
