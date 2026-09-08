---
name: measure
description: >
  Audits code for risk using complexity, coverage, and structural metrics (CRAP score,
  file-level hidden complexity) instead of a line-by-line read. Use this whenever the
  user asks how risky, complex, or well-tested a change is, wants a codebase health
  check, is deciding whether code is safe to merge or ship, or wants AI-generated code
  audited before trusting it — even if they don't name a specific metric or say
  "code quality" outright (e.g. "is this function too complicated", "how confident
  should I be in this PR", "did the agent leave a mess anywhere"). Language-aware:
  detects the project's language and dispatches to the matching reference for concrete
  tools, prerequisites, and thresholds — say so and stop rather than guessing a tool
  chain for a language with no reference yet. Distinct from language-specific
  engineering skills (e.g. rust-engineer) — this skill verifies after the fact and
  reports findings; it never writes or fixes code itself.
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
   detects the language and dispatches to `assets/<language>/run.sh`, which
   itself does three things: **discovery** (checks which metrics have their
   required tools on `PATH`, prints a minireport of available vs. missing
   before anything runs), **fan-out** (each available metric runs as its own
   independent process, in parallel with the others — see
   `references/<language>.md` for the one case, CRAP, that isn't fully
   independent), and **summary** (every branch's report, printed together).
   It exits nonzero and names what's missing if a required tool isn't on
   `PATH`; it does not install anything. Being plain shell, it's callable
   identically by a human, CI, or any other agent — not just this skill.
5. **Spot-check before reporting.** For at least the highest-scoring finding
   per metric, read the actual file/function named — a raw threshold crossing
   is not the same as a confirmed risk. See "Running this across agent hosts"
   below for the fuller adversarial-verification version of this step.
6. **Report findings** as a structured list: file, function/line, metric, score,
   threshold, severity. No silent caps — if scope was limited (one package, a changed-file
   subset), say so in the report.
7. **Hand the findings off.** This skill does not fix anything. Pass the report to
   the relevant engineering skill/session, or to the user, to act on.

## Running this across agent hosts

`assets/run.sh` is the one thing every host runs identically — plain shell,
no LLM dependency, does discovery + parallel fan-out + summary on its own.
What differs across hosts is the _verification_ layer on top of it: fanning
out one skeptic subagent per flagged finding (mirrors this org's own
code-review pattern — parallel reviewers, then a confidence-scored filter
before anything gets reported) needs each host's own orchestration
primitives, since there's no cross-host standard for that part.

- **Claude Code**: `assets/measure.workflow.js` is a self-contained
  `Workflow` tool script — run metrics, extract findings, then verify each
  in parallel with a skeptic subagent (default-low-confidence, filtered at
  ≥80). It's opt-in, not run automatically: only pass it to the `Workflow`
  tool when the user has actually asked for multi-agent orchestration (per
  that tool's own usage rules). Invoke with
  `Workflow({script: <contents of assets/measure.workflow.js>, args: {manifestDir: <path>}})`.
- **OpenCode**: `opencode/command/measure.md` + `opencode/agent/measure-verify.md`
  are the equivalent pair, expressed in OpenCode's own command/subagent
  format (verified against `opencode.ai/docs/agents` and `.../commands`, but
  not executed end-to-end — no OpenCode install was available to test
  against when these were written. Treat as best-effort until someone runs
  it for real).
- **Any other host**: fall back to `assets/run.sh` directly and do the
  verification step yourself per item 5 above — every host can at least do
  that much.

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
