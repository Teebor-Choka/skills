---
description: Run code-quality:measure, then adversarially verify every flagged finding before reporting it
agent: build
---

Locate the code-quality:measure skill's own directory — call it `$SKILL_DIR`. It contains
`assets/rust/run.sh` under a `code-quality/workflows/measure` path (check `.opencode/skills/`,
`~/.config/opencode/skills/`, `.claude/skills/measure`, or `~/.claude/skills/measure`) — then run,
anchored to that directory, not the current one:

    $SKILL_DIR/assets/run.sh ${ARGUMENTS:-Cargo.toml}

That script prints a discovery minireport (which metrics are `[available]` vs `[missing]`),
then runs every available metric in parallel, then a per-metric summary. Read the output and
extract every finding that crossed its own printed threshold (CRAP score above the printed
threshold, FileRisk above the printed threshold). Do not fabricate a finding for a metric the
discovery step reported `[missing]` — note that instead.

For each finding, dispatch the `measure-verify` subagent with the finding's metric, file,
function, line, score, threshold, and the manifest path (`${ARGUMENTS:-Cargo.toml}`) so it doesn't
have to rediscover where to resolve the finding's file path from. Only report findings it scores at
confidence 80 or above — it's instructed to default to skepticism, so a low score means treat the
finding as a false positive or acceptable complexity, not an error worth surfacing.

Summarize: confirmed findings (with the confidence and one-line reasoning `measure-verify` gave
each), and how many were filtered out as unconfirmed.
