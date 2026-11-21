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
reviewable. The detail lives in two references; read the one for what you're doing.

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

- Work in a git worktree off the most recent `origin` version of the target branch. `git fetch
origin` first and branch from `origin/<default>` (not the local branch), so a stale base
  doesn't produce unintended diffs in the PR.
- Place the worktree in the repo's `.claude/` (Claude Code) or `.agents/` (other agents)
  directory, and name it with the branch convention below from the start.
- Run `git worktree list` before `git worktree add`. If the branch already has a worktree, work
  there: git refuses a second checkout of one branch. Run `direnv allow` only for the repo's own
  `.envrc` (see Related skills).
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

You own a PR you opened until it merges or is closed, not until it is pushed. Babysitting is the
default straight after `gh pr create` or a push to a PR branch, and what "babysit this PR" or
"babysit PRs" asks for. Never hand-roll a `sleep N && gh pr view` loop, and never use
`ScheduleWakeup` to re-check a PR: each one re-reads your whole context to learn that nothing
changed. Use `pr-state` for a single look.

1. Start `scripts/babysit --heartbeat 600 [BRANCH]` as one long-lived background watcher, one per PR,
   in a mode that streams each output line to you as it prints: a watch tool that has no expiry, not
   a one-shot background job whose output arrives only at exit. If the host's watch tool expires
   after a fixed time, every re-arm costs a full-context turn, so use the longest timeout it allows
   and a heartbeat. On Claude Code that is `Monitor {command: "scripts/babysit --heartbeat 600
<branch>", timeout_ms: 1800000, description: "babysit PR N"}` (load it first with `ToolSearch
select:Monitor`; its schema is deferred). Add `persistent: true` only when the schema offers it:
   some versions cap the watch at 30 minutes. The watcher picks the forge from origin's host (or `--forge`), loads only that backend, makes one API call
   a minute and prints only changes, one JSON line each:
   `snapshot`, `comment`, `thread`, `review`, `checks`, `merge`, `enqueued`, `enqueue_failed`,
   `heartbeat`, then `merged`, `closed` or `error`. Its header documents the fields. `--heartbeat`
   adds a status line after that many quiet seconds; set it when someone wants periodic progress.
   Start it once your implementation is complete: on a draft the first poll marks it ready
   (`ready` event). Ready means the implementation is complete and feedback is requested. It does
   not predict CI or review results; those arrive afterwards as events, and the PR stays ready
   while you address them.
2. Every review, comment, thread reply and check result (once per new commit) reaches you as a
   line. Act on each one as it arrives, with the procedure that already covers it
   (`references/pull-requests.md`):
   `thread`/`review`/`comment` → address the feedback; `checks` with failures → fix and push;
   `merge` `BEHIND`/`DIRTY` → merge or rebase onto the target; `merge` `CLEAN` with approval →
   tell me it is ready. Events with `"self": true` came from the logged-in account, which may be
   me: skip only the ones you just posted.
3. If the watcher stops before `merged`/`closed` (a host timeout, a session restart), read its
   state file `.git/babysit/<branch>.json` (and the `.stderr` beside it) first, because it may
   already hold the failure. Then start it again. A host expiry (Claude Code: a notice
   after the timeout, or exit 144) is routine: re-arm at once, because a PR can fail unnoticed while no watcher runs. The state file keeps old
   events from repeating.
   A check that fails on two unrelated PRs is not a rerun case. Name one owner, get a repro, and
   do not run `gh run rerun` blind.
4. Stop at `merged`, `closed`, or `error` (report it). On `merged` the watcher runs `pr-landed`
   itself and prints its result (`--no-land` keeps the branch and worktree). Babysitting never
   merges on its own: the merge stays mine, UNLESS the repo being watched has
   `git config babysit.automerge true` set — a standing, repo-wide grant I gave for that one repo
   specifically, never inferred from a single approval or set globally. With it set, babysit
   enqueues the merge itself the first poll the PR is clean (approved, checks green, zero
   unresolved threads), prints `enqueued` (or `enqueue_failed`), and keeps watching for `merged` as
   usual. Never set this config yourself without that explicit, repo-scoped grant.

The watcher's exit or event line is the only wait signal. A dead watcher shows as a missing
heartbeat line: re-arm it. Do not read the checks by hand to see whether it is stuck.

For a silent wait, `babysit --quiet` prints only the final event (and `pr-landed`'s result). Other skills that drive a PR (swe-workflows `implement`, builders under `harness:assign` or
`harness:pull`) use this procedure rather than their own loop.

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
