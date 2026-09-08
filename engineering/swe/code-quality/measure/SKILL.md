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

A language engineering skill (e.g. `rust-engineer`) runs inline, on every edit,
cheaply. This skill runs expensive, batch-shaped checks — generating coverage,
scoring every function — so it belongs at a deliberate checkpoint instead: before
a commit, before a PR, or as a periodic health check, never on every edit. It only
reports; a human or the engineering skill decides what to do about a finding.

## Process

1. **Detect the language** — `Cargo.toml` → Rust, `package.json` → JS/TS,
   `pyproject.toml`/`setup.py` → Python, `go.mod` → Go, etc.
2. **Read `references/<language>.md`** for the tool chain, formulas, and
   thresholds. No reference yet for a language → say so and stop; don't invent
   tooling on the spot.
3. **Check the dev environment** (nix devShell, CI config) for the tools the
   reference requires. Missing → propose the setup diff, don't install silently.
4. **Run `assets/run.sh <path>`** — plain, deterministic shell, no LLM involved.
   It detects the language, dispatches to `assets/<language>/run.sh`, and does
   discovery (which metrics have their tools available), parallel fan-out (each
   available metric, independently), and a combined summary. See
   `references/<language>.md` for exactly what it runs. Callable identically by
   a human, CI, or any other agent, not just this skill.
5. **Spot-check the highest-scoring finding per metric** by reading the actual
   file/function — a threshold crossing isn't a confirmed risk on its own. See
   "Verifying findings across hosts" below for the fuller version of this step.
6. **Report findings**: file, function/line, metric, score, threshold, severity.
   Say so if scope was limited (one package, a changed-file subset).
7. **Hand off.** This skill never fixes anything — pass the report to the
   engineering skill or the user to act on.

## Verifying findings across hosts

`assets/run.sh` runs identically everywhere. What differs is the verification
layer on top of it — fanning a skeptic subagent out per flagged finding, filtered
by confidence, mirroring this org's own code-review pattern of parallel reviewers
plus a confidence filter. Each host needs its own version; there's no cross-host
orchestration standard for this part:

- **Claude Code** — `assets/measure.workflow.js`, a self-contained `Workflow`
  tool script. Opt-in only: pass it to `Workflow` when the user has actually
  asked for multi-agent orchestration, per that tool's own usage rules. Resolve
  this skill's own directory (the one containing this SKILL.md) first and pass
  it as `skillRoot` — the workflow can't locate its own assets itself, only an
  agent can, and you already know the path. Invoke with
  `Workflow({script: <contents of assets/measure.workflow.js>, args: {manifestDir: <path>, skillRoot: <this skill's directory>}})`.
- **OpenCode** — `opencode/command/measure.md` + `opencode/agent/measure-verify.md`,
  the equivalent pair, written against OpenCode's documented command/agent
  schema but not run end-to-end (no OpenCode install available to test against).
  Treat as best-effort until someone runs it for real.
- **Any other host** — fall back to step 5 above.

## Language reference index

| Language | Reference                                | Status                                                         |
| -------- | ---------------------------------------- | -------------------------------------------------------------- |
| Rust     | [references/rust.md](references/rust.md) | Covered — CRAP score + file-level hidden complexity            |
| Others   | —                                        | Not yet researched — do not guess; ask before running anything |
