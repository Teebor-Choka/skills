#!/usr/bin/env python3
"""SubagentStart hook: subagents do not inherit the parent's CLAUDE.md or output style, and they hit the same
hook and harness walls the main session does (368 refusals in 30 days, 357 of them in subagents: foreground
`sleep`, PR polling, compound commands in a worktree). Re-inject the house rules at spawn.
Injects additionalContext only; never blocks. The payload is not read, so bad input still injects.
Tests: hooks/tests/test_subagent_rules.py.
"""
import json

CONCISE = ("Report concisely: lead with the answer or findings, drop preamble, restated task context, and "
           "filler, and use no decorative structure. Plain human voice, no em-dashes, no canned openers or "
           "closers, no sycophancy. Keep every exact string, error, path, and caveat intact. Return only what "
           "the task asked for.")
RULES = (" Never wait with a foreground `sleep` (5 s or less is fine) and never poll `gh pr view` or "
         "`gh pr checks`: use run_in_background, or Monitor with an until-loop (Monitor is deferred: load it "
         "first with ToolSearch select:Monitor). In a worktree use one plain command per Bash call: no `cd X;`, "
         "`$(...)`, `bash -c`, eval, or variable-built command names; use `git -C <path>`, and put multi-step "
         "logic in a script file you write first and then run.")

print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": CONCISE + RULES}}))
