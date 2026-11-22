# Worktrees

Read when creating, using or pruning a worktree.

- Work in a git worktree off the most recent `origin` version of the target branch. `git fetch
origin` first and branch from `origin/<default>` (not the local branch), so a stale base
  doesn't produce unintended diffs in the PR.
- Place the worktree in the repo's `.claude/` (Claude Code) or `.agents/` (other agents)
  directory, and name it with the branch convention in SKILL.md (Branches and commits) from the start.
- Run `git worktree list` before `git worktree add`. If the branch already has a worktree, work
  there: git refuses a second checkout of one branch. Run `direnv allow` only for the repo's own
  `.envrc` (see Related skills in SKILL.md).
- `cd` into the worktree explicitly in every command. Run from outside it and tools and reads
  resolve to the git root instead, and the working directory doesn't persist across invocations.
- The Claude Code `EnterWorktree` tool names the branch `worktree-<name>`. Rename it to the branch
  convention (`git branch -m`) before the first push: the name lands on the remote and in the PR.
- An isolated worktree session refuses `cd <dir> && git ...` and compound or variable-built git
  commands. Use `git -C <path> <cmd>` and one plain command per call. Edit files with the Edit
  tool, not `sed -i` (GNU and BSD flags differ).
- After `worktree add` or `EnterWorktree`, use paths under the worktree root only. Re-read every
  file you will edit by its worktree path before the first edit. A read of the same repo-relative
  path under the main checkout does not count.
- Some repos are worked on a branch in the main checkout, not a worktree — honor the repo's own
  convention when it has one (it's usually there because per-worktree state is costly or fragile:
  a `direnv`/nix dev shell, a decrypting-secrets tooling layer, or Terraform/Terragrunt state that
  doesn't want a second tree). Default to a worktree; switch to a branch-on-main where the repo
  says so, one change at a time.
- Agent worktrees under `.claude/worktrees/` (or `.agents/`) each carry a full build tree (a Rust
  `target/` alone has reached tens of GB across a few worktrees). Prune worktrees you're done with
  (`git worktree remove`), and prune the ones whose `target/` has grown large even if the branch
  is still open — the branch survives the worktree.
