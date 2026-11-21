---
description: Orchestrator pickup of a handoff or issue (restate state, budget, done-when)
argument-hint: "<handoff path or issue> [next item] [budget] [done-when] [peer]"
---

Goal: pick up `$ARGUMENTS`.

If the argument is empty or vague, ask for scope first with one batched multi-choice question
(AskUserQuestion): handoff path or issue, next item, budget (hours or cost), done-when. Then
start.

- Read the handoff or issue. Restate state in 3 lines: done, open, blocked. Then name the next
  item and wait for correction only if the state is unclear.
- Scope: the next item named in the argument. Stop and ask when the work changes scope, passes the
  budget, or needs a decision.
- Done when: the done-when in the argument holds, with verification evidence (CI result, command
  output, PR link). If none is set, ask "what is the done-when?" before work.
- Expected duration and deadline: state both up front; compare with the budget and check progress
  against them.
- Escalate by message to the peer named in the argument, not by a blocking question dialog.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: work in a git worktree off origin/<default branch>, one worktree per concurrent
  worker. Never push to main. Merge authority: human only, or a grant stated in the argument.
  Never merge or tag without approval given in the moment.
