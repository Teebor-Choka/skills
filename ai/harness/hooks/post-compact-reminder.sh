#!/usr/bin/env bash
# SessionStart hook (compact): after context compaction, remind the agent that file state and plan state
# are gone. Injects additionalContext only; never blocks. Static JSON, so it needs no jq or python3: the
# text holds no quote or backslash (the test checks that the output parses).
set -euo pipefail
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Context was just compacted. Re-Read a file before you Edit or Write it (the harness forgets what you read). Re-read the plan, board item, or STATE file you were working from instead of trusting the summary for status, and keep the user steering instructions from the summary. Deferred tools you used before (SendMessage, Monitor, TaskStop, AskUserQuestion) must be reloaded with one batched ToolSearch select:A,B,C before the next use. Background task ids from before the compaction may be stale: list the running tasks before you stop one."}}'
