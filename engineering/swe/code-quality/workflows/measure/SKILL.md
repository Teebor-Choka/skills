---
name: measure
description: >
  Audits code for risk using complexity, coverage, and structural metrics instead of
  a line-by-line read. Use whenever asked how risky, complex, or well-tested a change
  is, for a codebase health check, when deciding if code is safe to merge or ship, or
  to audit AI-generated code before trusting it — even without the words "code
  quality" or a named metric (e.g. "is this function too complicated", "did the agent
  leave a mess anywhere"). Distinct from language-specific engineering skills (e.g.
  rust-engineer): this one verifies after the fact and reports findings, it never
  writes or fixes code.
---

# code-quality:measure

Audits code for risk using metrics, not a read-through. Reports findings, never edits
code. First skill in the `code-quality` family — the `measure` workflow here; siblings
(e.g. a future `fix` workflow) can join the same plugin without restructuring this one.

## Why separate from the engineering skill

A language engineering skill runs inline, on every edit, cheaply. This one runs
expensive, batch-shaped checks, so it belongs at a deliberate checkpoint instead:
before a commit, before a PR, or as a periodic health check, never on every edit. It
only reports; a human or the engineering skill decides what to do about a finding.

## Process

1. **Detect the language** from the target's manifest — `Cargo.toml` → Rust,
   `package.json` → JS/TS, `pyproject.toml`/`setup.py` → Python, `go.mod` → Go, etc.
2. **Read `references/<language>.md`** for the tool chain, formulas, and thresholds.
   No reference yet → say so and stop; don't invent tooling on the spot.
3. **Find out what's actually installed.** Check each required tool's presence on
   `PATH` — don't assume any particular way they got there (nix, a system package
   manager, a language-native installer). Missing → say what's missing and how the
   reference suggests getting it; don't install anything yourself.
4. **Run `assets/run.sh <manifest-path>`** — plain, deterministic shell, no LLM
   involved. It detects the language from the manifest, dispatches to
   `assets/<language>/run.sh`, and does discovery (what's available), parallel
   fan-out (each available metric, independently), and a summary. Callable
   identically by a human, CI, or any other agent, not just this skill.
5. **Spot-check the highest-scoring finding per metric** by reading the actual
   file/function — a threshold crossing isn't a confirmed risk on its own. See
   "Verifying findings across hosts" for the fuller version of this step.
6. **Report findings**: file, function/line, metric, score, threshold, severity.
   Say so if scope was limited.
7. **Hand off.** Never fixes anything — pass the report to the engineering skill or
   the user.

## Verifying findings across hosts

`assets/run.sh` runs identically everywhere. What differs is the verification layer
on top — fanning a skeptic subagent out per flagged finding, filtered by confidence,
mirroring this org's own code-review pattern. Each host needs its own version;
there's no cross-host orchestration standard for this part:

- **Claude Code** — `assets/measure.workflow.js`, a `Workflow` tool script. Opt-in
  only, per that tool's own usage rules. Resolve this skill's own directory first
  and pass it as `skillRoot` — the workflow can't locate its own assets itself, only
  an agent can. Invoke with `Workflow({script: <contents of
assets/measure.workflow.js>, args: {manifestPath: <path>, skillRoot: <this skill's
directory>}})`.
- **OpenCode** — same underlying pieces, different address: `code-quality:measure`
  is a Claude Skills convention OpenCode doesn't share, so there it's the `/code-quality`
  command (`opencode/command/code-quality.md`) plus the `measure-verify` subagent
  (`opencode/agent/measure-verify.md`). Unlike the Claude Code workflow, the command
  isn't a fixed pipeline — it describes the available tools and lets the agent use
  whichever the request calls for (a full audit, one metric, a spot-check). Written
  against OpenCode's documented schema but not run end-to-end (no OpenCode install
  available to test against).
- **Any other host** — fall back to step 5 above.

## Language reference index

| Language | Reference                                | Status                                |
| -------- | ---------------------------------------- | ------------------------------------- |
| Rust     | [references/rust.md](references/rust.md) | Covered                               |
| Others   | —                                        | Not yet researched — ask, don't guess |
