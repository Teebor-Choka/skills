---
description: Fix a PR or issue (template with scope, done-when, worktree rules)
argument-hint: "<PR or issue URL> [line: default|compat/v4] [port: yes|no] [done-when]"
---

Goal: fix `$ARGUMENTS`.

If the argument is empty or vague (no URL, no named repo), ask for scope first with one batched
multi-choice question (AskUserQuestion): target, line, port yes/no, done-when. Then start.

- A bare PR URL from inside its repo ("Fix <PR URL>") is valid as is: check out the PR branch and
  fix what its review comments and CI name. No extra questions.
- An issue URL: ask or infer the line (default branch, or a release line such as compat/v4) and
  whether to port the fix to the other line. Name the test words and the line in the plan.
- Test first: write a failing test that reproduces the issue, then make it pass.
- Scope: this repo only. Stop and ask if the fix needs a change in another repo.
- Done when: CI is green and the PR links the issue. Show the check output as evidence. If the
  argument sets no done-when, ask "what is the done-when?" before work.
- Expected duration and deadline: state both up front; check progress against them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: work in a git worktree off origin/<default branch>. Open a draft PR. Never push to
  main. Never merge or tag without approval given in the moment. Merge grant: as stated in the
  argument, or none.
- Autonomy: ask only before destructive actions.
