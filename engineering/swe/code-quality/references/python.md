# Python — Code Quality Metrics

## Metrics tracked

| Metric               | Tracks                                                                                                                                                                                                       | Tool                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| CRAP                 | Per-function risk combining cyclomatic complexity with how untested it is                                                                                                                                    | `crap4py`                            |
| Cognitive Complexity | How hard a function actually reads to a human — penalizes nesting/breaks in linear flow, unlike cyclomatic complexity                                                                                        | `complexipy`                         |
| Hotspots             | Complexity × how often a file is actually touched — flags complex code that's also actively changing                                                                                                         | `complexipy` + `git log` (see below) |
| Duplication %        | Percentage of near-duplicate code across the project                                                                                                                                                         | `jscpd`                              |
| I/A/D                | Robert C. Martin's Instability/Abstractness/Distance from the Main Sequence — flags modules simultaneously concrete and heavily depended-on ("zone of pain"), or abstract and unused ("zone of uselessness") | `pyscn`                              |

No FileRisk equivalent exists for Python yet — no verified tool identified. Not
guessed at; see Known limitations below.

### Formulas

```
CRAP(m) = CC² × (1 − cov)³ + CC                    -- >30 flagged
Hotspot = touches × cognitive-complexity-sum, per file
I = Ce / (Ca + Ce)                                 -- instability, 0 (stable) .. 1 (unstable)
A = abstract classes / total classes               -- abstractness
D = |A + I − 1|                                    -- distance from the main sequence
```

CRAP is the same formula Rust's `cargo-crap` uses — this is the same metric, not a
reimplementation, so CRAP scores are comparable across a repo with both languages.
`CC` cyclomatic complexity, `cov` fraction covered (branch coverage, not just line —
see Getting the tools below for why that distinction matters here). Cognitive
Complexity has no closed-form formula — it's an algorithm (nesting-weighted
control-flow walk) from G. Ann Campbell's original SonarSource whitepaper. `touches`
comes from `git log`, the complexity term from `complexipy` — see
`assets/lang/shared/hotspots.sh` for why Hotspots is a join rather than a dedicated
tool. `Ca`/`Ce` are afferent/efferent coupling (how many other modules depend on this
one / how many this one depends on).

## Tool choice, and why

**`crap4py`** — verified real PyPI package (MIT license), a port of the same CRAP
tool family already used for Rust and other languages. Consumes an `--lcov` file
directly, the same interface `cargo-crap` uses, produced here via `pytest-cov`
wrapping `coverage.py`.

**`complexipy`** (MIT) — actively maintained, Rust-implemented-as-a-PyO3-binding so
it's fast and standalone (no project build needed). The alternative,
`flake8-cognitive-complexity`, is real but abandoned (last pushed 2021) and
threshold-only — no per-function score export, only a lint pass/fail. Also used for
Hotspots' complexity term, so no separate tool needed there.

**`jscpd`** (MIT) — the same tool used for Rust's Duplication %, one consistent
percentage across both languages rather than a separate per-language tool.

**`pyscn`** (MIT) — actively maintained, and the only tool found that computes
Martin's actual formulas rather than something adjacent: confirmed its own real field
names (`afferent_coupling`, `efferent_coupling`, `instability`, `abstractness`,
`distance`) directly against a live run, not just its docs. It resolves Python's
abstract/concrete ambiguity (Python has no formal `abstract`/`concrete` type
distinction the way a trait/struct split gives Rust one) by counting a class as
abstract only if it inherits from `abc.ABC` — not `typing.Protocol`, not
duck-typing — a real, documented convention choice, not this skill's own guess.

## Ruled out

- **`flake8-cognitive-complexity`** — see above.
- No Rust-equivalent gap for Duplication % or Hotspots — the same tools/approach
  cover both languages.
- No I/A/D alternative was found worth ruling in — `pyscn` was the first and only
  Python tool checked that computes Martin's actual formulas (as opposed to
  producing an adjacent dependency graph with no numeric score).

## Getting the tools

`pip install crap4py pytest pytest-cov complexipy pyscn` (or the project's existing
dependency manager — poetry, uv, pip — this doesn't assume one; `pyscn` also ships as
`pipx install pyscn` / `uvx pyscn`). `pytest-cov` wraps `coverage.py`'s
branch-coverage mode; **`--cov-branch` must be passed** when generating coverage, or
the coverage fraction `crap4py` consumes only reflects line coverage, not branches —
a correctness detail, not a formatting one, since the CRAP formula's `(1 − cov)³`
term is only meaningful against the same coverage definition the formula was designed
around. `jscpd` needs Node.js, Cargo, or Homebrew (`npm install -g jscpd` /
`cargo install jscpd` / `brew install jscpd`) — it isn't a Python package. Hotspots
additionally needs `jq` (any package manager) to join its churn/complexity data, and
a real, non-shallow git working copy for the target project (see Known limitations
below).

Verified end-to-end in a real environment this session: a Python 3.13 venv
provisioned via `nix shell nixpkgs#python3`, with every tool above installed via
`pip install`, running against real fixtures — confirmed
`pytest --cov --cov-branch --cov-report=lcov:...` produces a real LCOV file with
branch records and `crap4py <dir> --lcov <path>` scores it correctly; `complexipy`,
`jscpd`, and `pyscn` were each run directly against a fixture with a known-shape
answer (an intentionally duplicated function, an `abc.ABC` subclass, a two-module
import) and produced the expected values.

## Invocation

`assets/run.sh <pyproject.toml-path>` (or combined with a Rust manifest for a
multi-language repo: `assets/run.sh Cargo.toml pyproject.toml`). `crap.sh` accepts a
pre-generated lcov file as a second argument to skip regenerating coverage, same as
Rust's. Each metric script under `assets/lang/python/` is also independently
runnable.

## Known limitations

- **No FileRisk equivalent.** Open gap, not guessed at — extend this reference once
  a real tool is verified, the same standard CRAP and FileRisk were held to for Rust.
- **`pytest-cov` presence isn't verifiable via `command -v`.** It's a pytest plugin,
  not a standalone binary — discovery can report `[available]` for `python:crap` even
  when `pytest-cov` specifically is missing, and the actual failure only surfaces at
  run time inside `crap.sh`.
- **`crap.sh` doesn't parse `pyproject.toml`.** It treats the manifest's own directory
  as both the test root and the coverage-measurement root, rather than reading a
  `[tool...]` section for a `src/`-layout convention. An explicit assumption, not a
  silent one — projects with a non-flat layout may need a different invocation until
  this is revisited.
- **`pyscn`'s abstractness counts `abc.ABC` subclasses only.** A codebase relying on
  `typing.Protocol` or plain duck-typing for its abstractions won't show up as
  abstract in the `A` term — a real convention choice in the tool, not a bug, but
  worth knowing before reading a module's `D` score as definitive.
- **Hotspots requires a real git working copy.** Churn counting needs `.git`
  history — a bare checkout, tarball, or shallow clone (`git clone --depth`) has none
  or an incomplete one; `hotspots.sh` checks for both and reports a clear skip rather
  than a misleadingly low (or zero) score.
