---
description: Review a PR (findings in chat only, no push, no comments)
argument-hint: "<PR URL> [against <issue>] [line: default|compat/v4]"
---

Goal: review `$ARGUMENTS`.

If the argument has no PR URL or is vague, ask for scope first with one batched multi-choice
question (AskUserQuestion): PR, linked issue, line, focus areas. Then start.

- Read all comments and the linked issue first. Establish facts before judging.
- Output: findings ordered by severity. Each has file:line and the test that would catch it. Say
  "no findings" per area if none.
- Do not push, comment on the PR, approve, or request changes. Findings stay in this chat.
- Done when: the findings are posted in this chat, each with evidence (diff line, test run, or
  command output). If the argument sets another done-when, follow it.
- Expected duration and deadline: state both up front for large PRs; check progress against them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: to run code, use a git worktree off origin/<default branch> (or the PR head). Never
  push to main. Never merge or tag without approval given in the moment. Merge grant: as stated in
  the argument, or none.
