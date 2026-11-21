---
description: Read-only investigation with one defined output (no edits, no next step)
argument-hint: "<question> [output format] [save to <file>]"
---

Goal: answer `$ARGUMENTS`.

If the question is empty or vague, ask for scope first with one batched multi-choice question
(AskUserQuestion): exact question, branches or lines to cover, output format, file to save to.
Then start.

- Read only. No edits to the repo, no pushes, no PRs, no deploys. Writing the output file named in
  the argument is the one allowed write; put it outside the repo unless told otherwise.
- Output: the one artifact the argument names (for example a table with crate, repo, line,
  version). Cite file:line or command output for each fact. Mark unverified items as unverified.
- Stop condition: stop when the output is delivered. Do not plan or start the next step; wait for
  the next request.
- Done when: the output exists and each row has evidence. If the argument sets no output, ask
  "what is the done-when?" before work.
- Expected duration and deadline: state both up front for long runs; check progress against them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: if a checkout is needed, use a worktree off origin/<default branch>. Never push to
  main. Never merge or tag.
