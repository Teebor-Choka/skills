---
name: workflow
description: >
  Run before any git or gh state change: commit, push, branch, worktree, open or update a PR,
  babysit a PR, review threads, merge conflict, rebase, force-push. Holds the house rules (no
  push to main, no git add -A, no merge or tag unasked).
license: MIT
compatibility: any
---

# Git workflow

How git and GitHub pull-request work is done here, so `main` stays clean and every change is
reviewable. The detail lives in the references; read the one for what you're doing.

## Non-negotiables

These hold on every change, even when git is incidental to a larger task:

- **Never `git push origin main`** (or the target repo's default branch) directly. Work on a
  worktree/PR branch and open a PR. Scale the ceremony to the change, but never commit to main.
- **Never `git add -A` / `git add .`** — stage explicit paths by name, or `git add -u`. Blanket
  adds have swept generated artifacts into commits (a backup tarball, a `nix build` result
  symlink) and picked up worktree subdirectories as git submodules.
- **Never `gh pr merge` or create/push a tag without explicit, in-the-moment approval.** Branch,
  commit, push, and open draft PRs freely; stop before merge or tag. An earlier "merge and tag"
  OK does not carry forward to later PRs or releases — ask per action. This binds subagents too:
  a subagent never runs `gh pr merge` or creates/pushes a tag, whatever its task says (a runaway
  one once merged four PRs unapproved). When installed, a `PreToolUse` `git-guard` hook blocks
  merge, tag, and blanket-add commands; don't rely on it, the rule holds without it.
- **Waiting for CI or review: run `scripts/babysit` as a streaming background watcher** (see
  "Babysitting a PR until it merges"). Never wait with `sleep`, a `gh pr view`/`gh pr checks`/`gh api`/
  `gh run list` loop, or a timer wake that re-reads your context.
- **Before staging, verify no local/secret files are included** (`.claude/*.local.*`, `.env*`,
  credentials).

(These are also carried in the always-on instructions; restated here so a reader of this skill
sees them without going looking.)

## Worktrees

Read `references/worktrees.md` when creating, using or pruning a worktree (base on fresh `origin`,
location, `git -C` in isolated sessions, branch-on-main repos, pruning).

## Branches and commits

- Branch naming: `<nick>/<type>/<component>/<dash-separated-description>` (e.g.
  `kauki/feat/session/1-hop-integration-test`). Resolve `<nick>` from `git config --get
customAgents.nick`, falling back to the `GIT_CONFIG_CUSTOMAGENTS_NICK` environment variable, then to
  `agent`. On first use in a repo, pin the nick with `git config --local customAgents.nick <nick>`
  only when it came from the env var and no config value exists. Never pin the `agent` fallback or
  a name guessed from the OS user or the git author, and never override a configured global nick.
- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`), kept atomic and focused, with
  meaningful messages.
- Run tests, lint, and format before committing — don't commit something that fails them. Run
  `nix fmt` (or the repo's formatter) and the repo's validator before the first push, not after CI
  fails on treefmt, prettier, or a skills-validate check.
- Bump the version to match the change's actual impact: patch for fixes and test-only changes,
  minor for non-breaking additions, major for breaking changes; skip only when nothing consumers
  see has changed.
- Before deleting or renaming a shared file, search the codebase for references so you don't
  break callers.

## Issues

Every GitHub issue gets a type. Pass `--type <name>` to `gh issue create`; when you touch an
existing issue that has none, set it with `gh issue edit <n> --type <name>`. Types are defined per
organization, so pick from the repo's own list rather than guessing a name:

    gh api graphql -F owner='{owner}' -F name='{repo}' \
      -f query='query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { issueTypes(first: 25) { nodes { name } } } }' \
      -q '.data.repository.issueTypes.nodes[].name'

A repo owned by a personal account has no issue types (`issueTypes` is `null`); say so when you
file there instead of silently skipping the type.

## Pull requests

Draft-PR conventions, the after-every-push update rule, the review-thread reply/resolve
procedure, stacked-PR retargeting, and multi-repo stacks are in `references/pull-requests.md`. Read
it when opening or updating a PR, handling review feedback, or after a PR merges. It also covers
proof for claims in a PR body and checking many PRs with one call.

Report contract: the final message of a git task carries verified evidence (the check you ran and
its result) and the artifact link (for example the PR URL).

PR scripts ship in `scripts/`:

- `babysit [BRANCH]`: the one change-request watcher (GitHub, GitLab; one file per forge in
  `scripts/forges/`); see the next section.
- `pr-state [BRANCH]`: one-shot status of a GitHub PR (review decision, unresolved threads, merge
  queue entry, latest run vs head SHA) and the next action. It never polls; `babysit` waits.
- `pr-landed`: clean up after a merge, fast-forward the default branch, remove the merged branch's
  worktree, delete the local and remote branch (remote-agnostic, pure git).

## Babysitting a PR until it merges

Read `references/babysit.md` when waiting on CI or review: the `scripts/babysit` streaming watcher,
its event lines and how to act on each, re-arming, and the automerge grant.

## Gotchas

Force-push (fetch first, pinned lease), history-extraction, and shell and scripted-edit traps (zsh
splitting and globs, `sed -i`, all-or-nothing multi-file edits) are in `references/gotchas.md`. Read
it when force-pushing, pulling a file out of history, or scripting edits. It also holds the default-branch, hook,
stale-task-id and connection-error rules. When the remote is GitHub, also read `references/github.md`
(`gh` exit codes, push-before-`gh pr create`, auto-merge after a force-push, squash-merge SHA traps).

## Related skills

- Rust `Cargo.lock` merge conflicts → the Rust skill the repo's policy names.
- `direnv allow` per worktree and nix-store-symlinked pre-commit config in a fresh worktree →
  the `nix` skill.
