# GitHub gotchas

Read only when the remote is GitHub: `gh` calls, auto-merge, squash-merge. Other forges skip this file.

## Force-push

- Force-pushing with `--force-with-lease` resets GitHub auto-merge — re-enable auto-merge after
  every force push.

## Squash-merge erases the feature SHA

- A GitHub squash-merge creates a new commit on the target branch and discards the feature
  branch's individual commits. Anything still pinned to a pre-merge feature SHA (a downstream
  `Cargo.toml` git ref, a `go.mod` pseudo-version, a submodule) then points at a commit not
  reachable from any branch — an "impostor commit". It may keep resolving from GitHub's object
  store for a while, so the breakage is silent until the object is GC'd.
- After a squash-merge, repin to the squash-merge commit on the **target branch**, never the
  feature SHA. Confirm with `git branch --contains <sha>`.

## `gh` and push order

- `gh pr checks` exits 8 while checks are pending. That is a normal state, not a failure. Read
  check state with `gh pr view --json statusCheckRollup` or `scripts/pr-state`. Never call bare
  `gh pr checks`.
- Push first, then open the PR: `git push -u origin HEAD`, then `gh pr create`. Otherwise `gh`
  fails with "you must first push the current branch".
