# Git gotchas

Traps that fail silently or in confusing ways. Read when force-pushing or pulling a file out of
history. GitHub-only traps (`gh`, auto-merge, squash-merge) are in `github.md`.

## Force-push

- Run `git fetch origin` immediately before any `--force-with-lease`. A bare lease compares
  against the remote-tracking ref, so a stale ref gives "stale info" or non-fast-forward rejections.
- Prefer the pinned form `git push --force-with-lease=<branch>:<expected-sha> origin <branch>`,
  with `<expected-sha>` the remote tip you just fetched (`git rev-parse origin/<branch>`). It
  fails only if the remote moved after that fetch.
- If it is still rejected, fetch and inspect `git log HEAD..origin/<branch>` before retrying. Fall
  back to plain `--force` only for a branch only you push to, after that check.

## Extracting a file from history

- `git show <rev> -- <path> > file` silently writes an **empty** file if the path doesn't exist at
  that revision. Verify the path resolves first with `git show <rev> -- <path> | head -1`.

## Default branch, hooks, tasks, connections

- Resolve the default branch with `git symbolic-ref --short refs/remotes/origin/HEAD`. Do not
  write `main` or `master`.
- In a repo with pre-commit hooks, run the hooks (`nix fmt` or `pre-commit run`) before `git commit`.
  Read a hook failure as formatting feedback.
- Before you stop a background task, list the running tasks and use the id from that list. A task
  id from before a compaction is stale.
- On "connection refused" or "Connection closed", retry once after a short wait. Then report which
  host failed and stop. Do not loop.

## Shell and scripted-edit traps

- **zsh does not word-split** an unquoted `$var`: `for r in $list` runs once with the whole list.
  Loop with `while read -r r; do ...; done <<<"$list"`, or run the block under `bash -c`.
- **zsh errors on an unmatched glob**: quote it (`--include='*'`) instead of leaving `*` bare.
- **`sed -i` differs**: BSD needs `-i ''`, GNU reads the `''` as a file name and fails. Do not use
  `sed -i`; use `perl -pi -e` or a short python script.
- **Edit several files all or nothing.** Stage every replacement, assert each `old` string matches
  exactly once, and write only when all match. Writing file by file with an assert in between leaves
  a half-edited set when a later match fails (a repo may ship a helper for this).
- **`git add -A` is blocked by the guard hook even inside test or heredoc text.** Stage explicit
  paths.
