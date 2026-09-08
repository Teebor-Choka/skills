# Verify rubric

The single source of truth for judging one flagged finding. Read by the verify step
on every host — Claude Code's `assets/measure.workflow.js` and OpenCode's
`opencode/agent/measure-verify.md` both point their verify agent at this file instead
of embedding the rubric text, so there's exactly one copy of the actual criteria.

Score confidence 0-100 that the finding is a genuine, actionable risk worth fixing —
not acceptable/inherent complexity, not a false positive. Default to LOW confidence
unless you have good reason to trust it. Read the actual file/function the finding
names before judging anything — resolve it relative to the given manifest's
directory, not your own working directory, since the two may differ.

Give one sentence of reasoning. Return only: confidence: <0-100>, reasoning: <one
sentence>.
