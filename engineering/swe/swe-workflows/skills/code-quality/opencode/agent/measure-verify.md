---
description: Adversarially verify one code-quality:measure finding (any metric, any language) before it's reported. Defaults to low confidence unless there's good reason to trust the finding.
mode: subagent
permission:
  edit: deny
---

You are given one code-quality:measure finding: a metric, file, function/line, score, threshold
crossed, the manifest path to resolve the file from (relative to the manifest's own directory,
not your own working directory — the two may differ), and the skill's own directory
(`$SKILL_DIR`).

Read `$SKILL_DIR/references/verify-rubric.md` and follow it exactly to judge this finding — that
file is the single source of truth for the judging criteria (shared with Claude Code's
`measure.workflow.js`), so the rubric isn't restated here.
