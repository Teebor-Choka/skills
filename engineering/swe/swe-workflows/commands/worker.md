---
description: Worker session under a coordinator (one task, report when the PR is open)
argument-hint: "<coordinator> [repo path] [task or issue] [merge authority]"
---

Goal: act as a worker for `$ARGUMENTS`.

If the argument lacks the coordinator, repo path, or task, ask for scope with one batched
multi-choice question (AskUserQuestion) before work. Do not wait idle for instructions.

- Read the repo's AGENTS.md first. Take only the task named; stay inside the repo path.
- Stop and message the coordinator when the task needs another repo, a scope change, or a
  decision. Escalate by message to the coordinator, not by a blocking question dialog.
- Done when: a draft PR is open, CI result is shown, and the coordinator has the PR link and the
  verification evidence by message (SendMessage). If a done-when is not given, ask for it.
- Expected duration and deadline: state both to the coordinator at start; report if you will miss
  them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: work in a git worktree off origin/<default branch>. Never push to main. Merge
  authority: human only, or a grant stated in the argument (for example, the coordinator arms
  auto-merge). Never merge or tag without approval given in the moment.
