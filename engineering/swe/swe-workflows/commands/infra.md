---
description: Infra change (plan output only unless apply is granted in the argument)
argument-hint: "<change> [repo] [environments] [apply grant] [done-when]"
---

Goal: `$ARGUMENTS`.

If the argument is empty or vague, ask for scope first with one batched multi-choice question
(AskUserQuestion): repo, environments, plan or apply, done-when. Then start.

- Default is plan output only. Do not apply. Apply only with a grant stated in the argument, or
  none.
- Scope: the named repo and environments. Stop and ask before any secret, state, or cross-repo
  change.
- Done when: a PR exists with the plan diff per environment. Paste the plan output as evidence. If
  the argument sets no done-when, ask "what is the done-when?" before work.
- Expected duration and deadline: state both up front; check progress against them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: work in a git worktree off origin/<default branch>. Open a draft PR. Never push to
  main. Never merge or tag without approval given in the moment. Merge grant: as stated in the
  argument, or none.
- Never log or commit secrets.
