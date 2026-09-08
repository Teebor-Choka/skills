---
name: measure
description: >
  Audits code for risk using complexity, coverage, and structural metrics (CRAP score,
  file-level hidden complexity, mutation testing) instead of a line-by-line read.
  Use before a commit or PR, as a periodic codebase health-check, or whenever asked to
  audit, gate, or score code quality/risk — especially code written by AI agents.
  Language-aware: detects the project's language and dispatches to the matching
  reference for concrete tools, prerequisites, and thresholds. Distinct from
  language-specific engineering skills (e.g. rust-engineer) — this skill verifies after
  the fact and reports findings; it never writes or fixes code itself.
---

# code-quality:measure

Audits code for risk using metrics, not a read-through. Produces a findings report;
never edits code. First skill in the `code-quality` family — siblings (e.g. a future
`code-quality:fix`) can be added under the same plugin without restructuring this one.

## Why this is a separate skill

Writing code and auditing it are different jobs at different cadences. A language
engineering skill (e.g. `rust-engineer`) runs inline, on every edit, cheaply. This
skill runs metrics that are expensive and batch-shaped — generating coverage, scoring
every function — so it belongs at a deliberate checkpoint instead: before a commit,
before a PR, or as a periodic pass. Keeping them separate also keeps the feedback
loop honest: this skill reports what it found, a human or the engineering skill
decides what to do about it.

## Process

1. **Detect the language(s) present** in the target — `Cargo.toml` → Rust,
   `package.json` → JS/TS, `pyproject.toml`/`setup.py` → Python, `go.mod` → Go, etc.
2. **Read the matching reference** under `references/<language>.md` for the concrete
   tool chain, formulas, and thresholds. If no reference exists yet for the detected
   language, say so and stop — do not invent tooling or thresholds on the spot.
3. **Check the target repo's dev environment** (nix devShell, CI config, or
   equivalent) for the tools the reference requires. If missing, propose the setup
   diff — do not install anything silently.
4. **Run `assets/run.sh <path>`** rather than assembling tool invocations from
   memory. It is a plain, deterministic shell script — no LLM involved — that
   detects the language, dispatches to `assets/<language>.sh`, and runs that
   language's tool chain in the order `references/<language>.md` specifies
   (cheapest / fewest prerequisites first). It exits nonzero and names what's
   missing if a required tool isn't on `PATH`; it does not install anything.
   Being plain shell, it's callable identically by a human, CI, or any other
   agent — not just this skill.
5. **Report findings** as a structured list: file, function/line, metric, score,
   threshold, severity. No silent caps — if scope was limited (one package, a changed-file
   subset), say so in the report.
6. **Hand the findings off.** This skill does not fix anything. Pass the report to
   the relevant engineering skill/session, or to the user, to act on.

## When to run this

On demand — before a commit or PR, or as a periodic health-check across a codebase.
**Not on every file edit.** Per-edit correctness and idiom is the engineering skill's
job; this skill's checks are too expensive to run at that cadence and answer a
different question (risk, not correctness).

## Language reference index

| Language | Reference                                | Status                                                         |
| -------- | ---------------------------------------- | -------------------------------------------------------------- |
| Rust     | [references/rust.md](references/rust.md) | Covered — CRAP score + file-level hidden complexity            |
| Others   | —                                        | Not yet researched — do not guess; ask before running anything |
