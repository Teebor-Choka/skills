---
name: my-skill
description: >
  ONE sentence on what this does, then the trigger contexts in the user's words — including
  casual phrasings that don't name the skill — and a short "do not use for …" clause. Keep it
  under 1024 characters and use no angle brackets. This text is the entire triggering signal on
  Claude Code, Codex, and OpenCode.
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# My skill

One or two sentences: what the skill lets the agent do, and the shape of a good run. Keep this
body agent-neutral — plain instructions, no hard-coded `Task(...)`, `@"x (agent)"`, or
`skill({...})` calls. Bind those in per-agent adapters, not here.

## When to use

Restate the trigger conditions and, importantly, the boundaries (what this is not for). This
helps the model both fire and stay quiet appropriately.

## Steps

1. Inputs — what you need and how to handle missing/empty input.
2. The work — the actual procedure, imperative, with the _why_ behind non-obvious steps.
3. Output — the exact definition of "done" (format, location).
4. Failure — what counts as failure and what to do then.

## Notes

- Push long lists, tables, or per-variant detail into `references/*.md` and point at them here
  with a one-line "read this when …".
- Put deterministic, repeated work into `scripts/` and call it instead of re-deriving it.
- Keep this file under ~500 lines.
