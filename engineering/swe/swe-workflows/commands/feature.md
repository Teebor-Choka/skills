---
description: Build a new feature (plan first, assumed scope shown, done-when)
argument-hint: "<feature> [copy: <existing>] [differences] [out of scope] [done-when]"
---

Goal: `$ARGUMENTS`.

If the argument is empty or vague, ask for scope first with one batched multi-choice question
(AskUserQuestion): what to copy from, differences, out of scope, done-when. Then start.

- Plan first. Before leaving plan mode, show one line: "Assumed scope: repos, hosts, secret paths".
  Wait for correction. Check for known site or host quirks before assuming a clean copy.
- Scope: the repos and files named in the plan. Out of scope: whatever the argument lists. Stop
  and ask if the work reaches beyond them.
- Build test first: failing test, then the least code that passes.
- Done when: the verifiable command named in the argument runs without error (for a host, its
  rebuild command). Show its output. If none is named, ask "what is the done-when?" before work.
- Expected duration and deadline: state both up front; check progress against them.
- Code first: when the repo is indexed, use the code-graph tool before grep or file reads.
- Branch rule: work in a git worktree off origin/<default branch>. Open a draft PR. Never push to
  main. Never merge or tag without approval given in the moment. Merge grant: as stated in the
  argument, or none.
