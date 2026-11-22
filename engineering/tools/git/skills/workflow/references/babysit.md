# Babysitting a PR until it merges

Read when waiting on CI or review for a PR you opened.

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
   (`pull-requests.md`):
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

For a silent wait, `babysit --quiet` prints only the final event (and `pr-landed`'s result). Other skills that drive a PR (an implement skill, builders under `harness:assign` or
`harness:pull`) use this procedure rather than their own loop.
