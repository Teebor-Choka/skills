---
description: Hand off to a fresh session for a new topic (5-line handoff, then clear)
argument-hint: "<next topic>"
---

Goal: close this topic and start `$ARGUMENTS` in a clean session.

If the next topic is empty or vague, ask for it with one batched multi-choice question
(AskUserQuestion) before writing the handoff.

1. Write a 5-line handoff to a file outside the repo (for example in the session scratchpad):
   goal, state, open items, branch or PR links, next step. Commit nothing.
2. Do not leave unpushed work or dirty worktrees unreported: list them in the handoff.
3. Tell me the handoff path, then ask me to run `/clear` (a command only I can run).
4. In the fresh session, start the next topic with the handoff path as the pointer.

- Scope: this session's state only. No new work, no edits to the repo.
- Done when: the handoff file exists, I have its path, and the next topic is named. Show the file.
- Code first: in the new session, when the repo is indexed, use the code-graph tool before grep.
- Branch rule for the next topic: work in a worktree off origin/<default branch>. Never push to
  main. Never merge or tag without approval given in the moment. Grant: as stated in the argument,
  or none.
