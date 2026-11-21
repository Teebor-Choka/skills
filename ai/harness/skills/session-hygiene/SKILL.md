---
name: session-hygiene
description: Handle the harness session nudges and write a handoff file when a session gets large. Use when a hook asks you to hand off or name the session, when context passes 700K tokens, when a session has compacted twice, or before ending a long session.
license: MIT
compatibility: any
---

# Session hygiene

The `harness` session hooks add context when a session needs attention. Act on each once.

## Hand off a large session

Cost per turn rises with context size. At about 700K tokens, or after a second compaction:

1. Write a handoff file of at most 15 lines next to the work: goal, state, decisions, next steps,
   open PRs and branches, file paths.
2. Tell the user the path.
3. Keep working. Do not stop or ask for a fresh session: autocompact carries the session on, and the
   file is the recovery point. Start a new session only at a boundary or when the user asks.

## Name the session

When the name nudge fires, suggest `<repo>-<issue-or-topic>-<role>` and ask the user to run `/rename`
with it. Ask once.

## Before a slow command

State the expected duration and a hard deadline in one line, run the command in the background with a
timeout, and report at the deadline instead of waiting on.

## After compaction

Re-read a file before you edit it, re-read the plan you worked from, and reload deferred tools in one
batched call.
