---
description: Code-quality toolkit for this project — audit risk via complexity/coverage/structural metrics, verify a specific finding, judge comment quality, or answer a question about a file/function/diff's risk. Tools and metrics vary by language. Not a single fixed pipeline — use whichever piece the request calls for.
agent: build
---

This is the code-quality toolkit for this project. Locate the `code-quality:measure`
skill's own directory first — it contains `assets/run.sh` under a
`code-quality/workflows/measure` path (check `.opencode/skills/`,
`~/.config/opencode/skills/`, `.claude/skills/measure`, `~/.claude/skills/measure`, or
search for a directory matching that layout). Call it `$SKILL_DIR`.

What's available:

- **`$SKILL_DIR/assets/run.sh <manifest-path> [<manifest-path> ...]`** — plain,
  deterministic shell. Detects each manifest's language, discovers which metrics have
  their tools installed, runs every available one across every detected language in
  one parallel batch, and prints a summary. Pass every manifest a project has in one
  call (e.g. both `Cargo.toml` and `pyproject.toml` for a mixed-language repo) to get
  the combined fan-out, not one command per language. Run it directly for a full
  pass, or call one of the language-specific per-metric scripts under
  `$SKILL_DIR/assets/lang/<language>/` to run just one metric — see
  `$SKILL_DIR/references/<language>.md` for what's actually available; don't guess
  a tool chain for a language with no reference yet.
- **The `measure-verify` subagent** — give it one finding (metric, file, function,
  line, score, threshold, the manifest path so it can resolve the file, and
  `$SKILL_DIR` so it can read the shared verify rubric) and it scores confidence
  0-100 that the finding is a genuine risk, defaulting to skepticism. Use it on any
  specific finding, not only ones a full run surfaced.
- **The `comment-quality` subagent** — give it one file path (plus `$SKILL_DIR` so
  it can read the shared comment rubric, and which lines changed if this is a diff)
  and it flags comments that restate the obvious, ramble, are missing where required
  (undocumented public API), or contradict/hedge against the code — each with a
  concrete proposed fix, not just a description of the problem. Qualitative, not a
  metric: no threshold, no score. Dispatch one per file, in parallel, for a
  multi-file review.

Use whichever of these the request actually needs — a full audit, one metric, a
spot-check on a single function, or just an explanation of what a score means. Don't
force a rigid "run everything, then verify everything" sequence unless that's what
was asked for.

If a full audit is what's wanted: run `assets/run.sh`, extract every finding that
crossed its own printed threshold from the output (don't fabricate one for a metric
the discovery step reported `[missing]`), dispatch `measure-verify` on each, and
report confirmed findings (confidence ≥ 80, with the reasoning it gave) plus how many
were filtered out — anything below that threshold is a false positive or acceptable
complexity, not an error worth surfacing.
