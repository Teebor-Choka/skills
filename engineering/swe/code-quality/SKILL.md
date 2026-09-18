---
name: code-quality
description: >
  Audits existing code for risk from complexity, coverage, duplication, and structural
  metrics plus a comment-quality pass — measured with real tools, not a line-by-line read —
  and verifies each flagged finding before reporting it. Use whenever asked how risky,
  complex, or well-tested code or a change is, for a codebase or PR health check, to decide
  whether something is safe to merge or ship, or to audit AI-generated code before trusting
  it — even phrased casually and without the words "code quality" or any metric name ("is
  this function too complicated", "how solid are the tests here", "did the agent leave a
  mess anywhere", "is this PR safe to merge", "which files are scariest to touch"). Reports
  findings only — it never writes, refactors, or fixes code. Do not use to actually change
  code (that is a language engineering skill such as rust-engineer), to run or write tests,
  or for security/vulnerability review.
---

# code-quality

Audits code for risk and reports findings — it never edits code. Three workflows, each with
its own assets and its own section below:

- **`measure`** — numeric metrics (complexity, coverage, duplication, structure) computed by
  real, JSON-emitting tools. Written for an agent to consume: its JSON is the primary
  interface, meant to feed back into an agent's judgment of how well code (its own or another
  agent's) was generated, not just to be looked at.
- **`report`** — the same numbers rendered as a human-readable table, for when a person is
  watching a terminal rather than an agent parsing output. This is why `measure`'s JSON never
  has to compromise between the two audiences.
- **`comments`** — a qualitative check on comment quality, since not every form of code risk
  is a number.

A future workflow is added the same way: a new section here plus new assets, not a separate
skill.

## Why separate from the engineering skill

A language engineering skill (e.g. rust-engineer) runs inline, on every edit, cheaply. This
one runs expensive, batch-shaped checks, so it belongs at a deliberate checkpoint instead:
before a commit, before a PR, or as a periodic health check — never on every edit. It only
reports; a human or the engineering skill decides what to do about a finding, and does the
fixing.

## The audit shape (portable intent)

A full audit is naturally parallel and two-staged — hold this shape regardless of which agent
runs it:

1. **Fan out over independent dimensions.** Each metric is a separate view of the same tree,
   so compute them concurrently, not one after another. For `measure` the per-metric fan-out
   already lives inside `assets/run.sh` (plain shell, no agent). For `comments` the
   dimensions are files: one reviewer per file, in parallel.
2. **Verify, then synthesize.** A threshold crossing is a _candidate_, not a confirmed risk.
   Fan a skeptic pass out per flagged finding — read the actual code, score confidence,
   default to low — keep only the confident ones, and synthesize a single report. This is the
   same find → verify → synthesize discipline the org's code-review uses.

That is intent, not mechanism. Each agent binds it to its own primitives (parallel subagents,
an orchestration script, or a plain sequential fallback) — see
[references/cross-agent.md](references/cross-agent.md). The verification criteria themselves
live in [references/verify-rubric.md](references/verify-rubric.md), read at runtime so there
is one copy.

## Process (the `measure` workflow)

1. **Detect the language(s)** from the target's manifest(s): `Cargo.toml` → Rust,
   `pyproject.toml`/`setup.py` → Python, etc. A project can have more than one — a repo with
   both a `Cargo.toml` and a `pyproject.toml` detects both, not one-or-the-other.
2. **Read `references/<language>.md`** for each detected language's tool chain, formulas, and
   thresholds. No reference yet for a detected language → say so and stop for that one; don't
   invent tooling on the spot.
3. **Find out what's actually installed.** Check each required tool's presence on `PATH` —
   don't assume how it got there (nix, a system package manager, a language-native
   installer). Missing → report what's missing and how the reference suggests getting it;
   don't install anything yourself.
4. **Run the orchestrator:**
   `assets/run.sh [--collection all|relevant] --manifest <path> [--manifest <path> ...]` —
   one `--manifest` per detected language. `--collection` chooses the metric set: `all`
   (default) runs every metric; `relevant` runs only the subset the field's authorities
   advocate (see `references/<language>.md`). It is plain, deterministic shell — no LLM — and
   does its own discovery, parallel fan-out (every available metric across every detected
   language in one batch, not one batch per language), and combined summary. Callable
   identically by a human, CI, or any agent. **stdout is pure JSON, nothing else** —
   `{discovery: {available, missing}, results: {"language:metric": {metric, language, unit, threshold, rows, summary}, ...}}`
   — parse it directly; there is no table or banner to strip. Metrics are labeled
   `language:metric` (e.g. `python:crap`) since two languages can share a metric name.
5. **Spot-check the highest-scoring finding per metric** by reading the actual file/function
   — a threshold crossing is not a confirmed risk on its own. This is the verify stage of the
   audit shape above; scale it up to a skeptic subagent per finding via
   [references/cross-agent.md](references/cross-agent.md), or do it inline when running alone.
6. **Report findings:** file, function/line, metric, score, threshold, severity. Say so if
   scope was limited.
7. **Hand off.** Never fixes anything — pass the report to the engineering skill or the user.

## Process (the `report` workflow)

Depends on `measure` — it computes nothing itself, it runs `measure` and formats the result.
Fully deterministic, so there is no per-agent divergence to document the way `measure`'s
verify stage and `comments` have.

1. **Run** `assets/report.sh [--collection all|relevant] --manifest <path> [--manifest <path> ...]`
   — same arguments as `assets/run.sh`, which it calls internally, formatting the JSON into
   the discovery banner plus per-metric tables a person reads in a terminal. Columns come
   straight from each metric's own JSON rows, so the table can never drift out of sync with
   what `measure` reports.
2. **Hand off** exactly like `measure` — `report` is a presentation layer over the same data
   and fixes nothing either.

## Process (the `comments` workflow)

Unlike `measure`, there is no deterministic tool to run first — judging whether a comment is
necessary, verbose, or missing where required is inherently a read-through, not a formula. So
this workflow is just: read files, judge, report.

1. **Pick the target files.** Usually the files a change actually touched (a diff, the files
   edited this session), not a whole-codebase sweep — comment quality matters most on
   new/changed code, and a full-repo pass is expensive for low value on code nobody is
   touching. Fall back to the full file list only if the request is explicitly a broader
   audit.
2. **Dispatch one reviewer per file, in parallel** — each reads
   [references/comment-rubric.md](references/comment-rubric.md) (the single source of truth
   for the rule; not restated here) and judges that one file against it. Per-agent
   invocation: [references/cross-agent.md](references/cross-agent.md).
3. **Report violations:** file, line, the comment's excerpt, which failure it is (restates
   the obvious, could be shorter, missing where required, or contradicts/hedges against the
   code), and a concrete proposed fix — the actual replacement wording or doc comment to add,
   not just a description of the problem. No violations is a valid, common result — don't
   manufacture one.
4. **Hand off.** Never applies a fix itself, even though it proposes one — pass the report to
   the engineering skill or the user, same as `measure`.

## References

Read on demand — keep this file lean and the detail where it belongs:

| File                                                         | Read it when                                                                      |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| [references/rust.md](references/rust.md)                     | Auditing Rust — the tool chain, formulas, thresholds, caveats, and getting tools  |
| [references/python.md](references/python.md)                 | Auditing Python — same, for its tool chain                                        |
| [references/verify-rubric.md](references/verify-rubric.md)   | Scoring confidence on a flagged `measure` finding (the verify stage)              |
| [references/comment-rubric.md](references/comment-rubric.md) | Judging comment quality in one file (the `comments` rule)                         |
| [references/cross-agent.md](references/cross-agent.md)       | Dispatching the parallel + verify passes natively on Claude Code, Codex, OpenCode |

### Language index (`measure` only)

`comments` applies one rubric to every language, so it has no per-language reference.

| Language | Reference                                    | Status                                |
| -------- | -------------------------------------------- | ------------------------------------- |
| Rust     | [references/rust.md](references/rust.md)     | Covered                               |
| Python   | [references/python.md](references/python.md) | Covered                               |
| Others   | —                                            | Not yet researched — ask, don't guess |
