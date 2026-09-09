---
name: code-quality
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

# code-quality

Audits code for risk. Reports findings, never edits code. Runs three workflows:
`measure` (numeric metrics — complexity, coverage, duplication, structure — backed by
real tools, output as JSON), `report` (a human-readable table rendered from
`measure`'s own JSON, for when a person is watching rather than an agent), and
`comments` (a qualitative check on comment quality, since not every form of code risk
is a number). Each is documented in its own section below, with its own assets —
`assets/run.sh` / `assets/measure.workflow.js` / `opencode/agent/measure-verify.md`
for `measure`, `assets/report.sh` for `report`, `assets/comments.workflow.js` /
`opencode/agent/comment-quality.md` for `comments`. A future workflow would be added
the same way: a new section here plus new assets, not a separate skill.

`measure` is written primarily for agents to consume — its JSON is the primary
interface, meant to feed back into an agent's own judgment of how well it (or another
agent) is generating code, not just to be looked at by a person. `report` exists
specifically for the secondary case, a human reading a terminal, so `measure`'s own
output never has to compromise between the two audiences.

## Why separate from the engineering skill

A language engineering skill runs inline, on every edit, cheaply. This one runs
expensive, batch-shaped checks, so it belongs at a deliberate checkpoint instead:
before a commit, before a PR, or as a periodic health check, never on every edit. It
only reports; a human or the engineering skill decides what to do about a finding.

## Process (the `measure` workflow)

1. **Detect the language(s)** from the target's manifest(s) — `Cargo.toml` → Rust,
   `pyproject.toml`/`setup.py` → Python, etc. A project can have more than one (a repo
   with both a `Cargo.toml` and a `pyproject.toml` detects both, not one-or-the-other).
2. **Read `references/<language>.md`** for each detected language's tool chain,
   formulas, and thresholds. No reference yet for a detected language → say so and
   stop for that one; don't invent tooling on the spot.
3. **Find out what's actually installed.** Check each required tool's presence on
   `PATH` — don't assume any particular way they got there (nix, a system package
   manager, a language-native installer). Missing → say what's missing and how the
   reference suggests getting it; don't install anything yourself.
4. **Run `assets/run.sh <manifest-path> [<manifest-path> ...]`** — one path per
   detected language. Plain, deterministic shell, no LLM involved: it detects each
   manifest's language, and itself does discovery (what's available, across every
   detected language), parallel fan-out (every available metric from every language,
   in one batch — not one batch per language), and a combined summary. Callable
   identically by a human, CI, or any other agent, not just this skill. **stdout is
   pure JSON, nothing else** — `{discovery: {available, missing}, results: {
"language:metric": {metric, language, unit, threshold, rows, summary}, ...}}` —
   parse it directly; there's no table to read or banner text to strip. Metrics are
   labeled `language:metric` (e.g. `python:crap`) since two languages can share a
   metric name. Want the human-readable version instead? That's `report`, below.
5. **Spot-check the highest-scoring finding per metric** by reading the actual
   file/function — a threshold crossing isn't a confirmed risk on its own. See
   "Running `measure`'s verify step across hosts" for the fuller version of this
   step.
6. **Report findings**: file, function/line, metric, score, threshold, severity.
   Say so if scope was limited.
7. **Hand off.** Never fixes anything — pass the report to the engineering skill or
   the user.

## Running `measure`'s verify step across hosts

`assets/run.sh` runs identically everywhere. What differs is the verification layer
on top — fanning a skeptic subagent out per flagged finding, filtered by confidence,
mirroring this org's own code-review pattern. Each host needs its own version;
there's no cross-host orchestration standard for this part:

- **Claude Code** — `assets/measure.workflow.js`, a `Workflow` tool script. Opt-in
  only, per that tool's own usage rules. Resolve this skill's own directory first
  and pass it as `skillRoot` — the workflow can't locate its own assets itself, only
  an agent can. Invoke with `Workflow({script: <contents of
assets/measure.workflow.js>, args: {manifestPaths: [<path>, ...], skillRoot: <this
skill's directory>}})`.
- **OpenCode** — same underlying pieces, addressed OpenCode's own way (it has no
  equivalent to Claude Skills' plugin:skill addressing): the `/code-quality` command
  (`opencode/command/code-quality.md`) plus the `measure-verify` subagent
  (`opencode/agent/measure-verify.md`). Unlike the Claude Code workflow, the command
  isn't a fixed pipeline — it describes the available tools and lets the agent use
  whichever the request calls for (a full audit, one metric, a spot-check). Written
  against OpenCode's documented schema but not run end-to-end (no OpenCode install
  available to test against).
- **Any other host** — fall back to step 5 above.

## Process (the `report` workflow)

Depends on `measure` — this workflow doesn't compute anything itself, it runs
`measure` and formats the result. No agent, no per-host divergence: it's exactly as
deterministic as `measure`'s own `assets/run.sh`, so there's nothing to document
per-host the way `measure`'s verify step and `comments` need.

1. **Run `assets/report.sh <manifest-path> [<manifest-path> ...]`** — same arguments
   as `assets/run.sh`, because it calls that script internally and formats its JSON
   into the discovery banner + per-metric tables a person would want to read in a
   terminal. Column set and order come straight from each metric's own JSON rows, so
   the table can never drift out of sync with what `measure` actually reports.
2. **Hand off** exactly like `measure` does — `report` doesn't fix anything either,
   it's a presentation layer over the same data.

## Process (the `comments` workflow)

Unlike `measure`, there's no deterministic tool to run first — judging whether a
comment is necessary, verbose, or missing where required is inherently a
read-through, not a formula. So this workflow is just: read files, judge, report.

1. **Pick the target files.** Usually the files a change actually touched (a diff,
   the files edited this session), not a whole codebase sweep — comment quality
   matters most on new/changed code, and a full-repo pass is expensive for
   comparatively low value on code nobody's touching. Fall back to the full file
   list only if the request is explicitly a broader audit.
2. **Dispatch one subagent per file, in parallel** — each reads
   `references/comment-rubric.md` (the single source of truth for the rule; not
   restated here) and judges that one file against it. See "Running `comments`
   across hosts" for the per-host invocation.
3. **Report violations**: file, line, the comment's excerpt, which failure it is
   (restates the obvious, could be shorter, missing where required, or
   contradicts/hedges against the code), and a concrete proposed fix — the actual
   replacement wording or doc comment to add, not just a description of the
   problem. No violations is a valid, common result — don't manufacture one.
4. **Hand off.** Never applies a fix itself, even though it proposes one — pass the
   report to the engineering skill or the user, same as `measure`.

## Running `comments` across hosts

- **Claude Code** — `assets/comments.workflow.js`, a `Workflow` tool script, one
  subagent per file in parallel. Same `skillRoot`-passing requirement as `measure`'s
  workflow. Invoke with `Workflow({script: <contents of
assets/comments.workflow.js>, args: {filePaths: [<path>, ...], skillRoot: <this
skill's directory>}})`.
- **OpenCode** — the `comment-quality` subagent (`opencode/agent/comment-quality.md`),
  dispatched once per file from the `/code-quality` command or directly. Written
  against OpenCode's documented schema but not run end-to-end (no OpenCode install
  available to test against).
- **Any other host** — dispatch a subagent per file directly, pointed at
  `references/comment-rubric.md`; there's no deterministic fallback the way
  `measure` has one (step 5 there), since this workflow has no non-agent step at all.

## Language reference index

For `measure` only — `comments` applies the same rubric to every language, so it has
no per-language references.

| Language | Reference                                    | Status                                |
| -------- | -------------------------------------------- | ------------------------------------- |
| Rust     | [references/rust.md](references/rust.md)     | Covered                               |
| Python   | [references/python.md](references/python.md) | Covered                               |
| Others   | —                                            | Not yet researched — ask, don't guess |
