# Pull requests

The PR conventions for this repo set. Read when opening or updating a PR, or handling review
feedback.

## Creating a pull request

- Validate first: format, lint, build, test.
- Open it as a **draft**.
- Description: high-level prose only — what changed and why, the essential concept and reasons.
  No implementation detail, no "Test plan". Bound the length by word count (~500 words; up to
  ~1000 if the change genuinely needs it), not by a fixed paragraph count, and use whatever
  structure reads best (headers, short paragraphs, the occasional list) to stay scannable.
  Describe only the final result — no review-iteration history ("earlier"/"latest", fix logs).
- When the PR changes `docs/**/*.md` in a repo that commits `docs/generated/`, run
  `render_docs.py --pr-summary` and paste its block into the description. It links the architecture
  view at the PR head SHA and carries the diagrams of the changed docs.
- Close issues with one `Closes #N` per line. A comma list or a prose reference closes only the first or none.
- Assign the PR to me (`--assignee @me`).
- Post the detailed implementation plan as a dedicated comment below the PR, never folded into
  the description.
- Post benchmark results as a follow-up comment, if applicable.
- Always paste the full `https://github.com/...` PR URL back after creating or updating it.
- Never include a Claude session link or an Artifact tool URL (`claude.ai/...`) in the description
  or any comment — strip them before posting.

## After every push on a PR branch

Immediately, without being asked:

1. Update the PR body (`gh pr edit --body`) if it needs it.
2. Update the implementation plan comment.
3. Make sure `babysit` is watching the PR (see "Babysitting a PR until it merges" in SKILL.md).

This is automatic and mandatory — the PR's description and plan should always match its current
state.

## Addressing review recommendations

1. **Merge the target branch first** — avoids stale-base conflicts and runs CI against current state.
2. **Fetch all unresolved threads** and classify: code changes vs questions needing a reply.
3. **Make all code changes**, run the full verification pipeline, commit and push.
4. **Reply** to each addressed thread via the GraphQL `addPullRequestReviewThreadReply` mutation
   (not `addPullRequestReviewComment`).
5. **Resolve** each addressed thread via the GraphQL `resolveReviewThread` mutation — REST does
   not support resolving threads.
6. Steps 4–5 happen immediately after the push, not on request. Cover every unresolved thread,
   not a subset — triage user-authored threads ahead of bot ones (Copilot/CodeRabbit). If a
   requested change is unreasonable or contradicts the codebase design, reply with the reasoning
   instead of applying it.

## Stacked PRs

A child PR is based on its parent's branch. When the parent squash-merges, the child still carries
the parent's old commits, so a plain rebase replays them and conflicts. Cut them off with `--onto`.
`git rerere` is enabled globally, so conflicts you resolve once replay automatically on later
rebases.

After a PR merges, retarget and rebase its children, one level at a time, parent first:

1. `git fetch origin`, then take the old parent tip from the merged PR:
   `gh pr view <parent-n> --json headRefOid -q .headRefOid` (works after the branch is deleted).
2. `git rebase --onto origin/<default> <old-parent-tip> <child-branch>`
3. Resolve and finish the rebase (`git rebase --continue`); never leave one interrupted. If it goes
   wrong, `git rebase --abort` and redo it from step 1.
4. Push with a pinned lease (see `gotchas.md`), then `gh pr edit <n> --base <default>`.
5. Repeat for the grandchild, using the child's old tip.

## After a PR merges

This skill ships the cleanup scripts in `scripts/`. Run `scripts/pr-landed`: it fast-forwards the
default branch, removes the merged branch's worktree, and deletes the local and remote branch
(squash-merge aware, refuses a dirty worktree). Read the old tip for any children first (stack step 1).

To wait for a PR to land and then clean up in one step **on GitHub**, run
`scripts/babysit --quiet [BRANCH]`: it prints nothing until the PR is merged, closed or
unreachable, and on a merge hands off to `pr-landed`. Use `gh run watch` to follow a specific CI
run. `babysit` needs the forge's CLI (`gh`, `glab`) and a backend in `scripts/forges/`;
`pr-landed` itself is remote-agnostic (pure git), so on a forge without a backend just run
`pr-landed` once the branch has merged.

## Multi-repo stacks

When a change spans repos, include dependency links in the PR descriptions (e.g. "Depends on:
#URL"). Propagate rebases strictly in dependency order across the stack, and update all caller
PRs after the dependency is merged and tagged. Present stack status as an ordered list or a
dependency diagram when asked.

A consumer branch is not deployable while it points at an unlanded dependency. Land the dependency
repo first and bump the consumer's lock (flake input, submodule, version pin) to the landed commit
before calling the consumer done. Before pushing the consumer, evaluate or build it **without** any
local override (e.g. `--override-input`, a path dependency, a linked checkout): an override hides a
lock that still names a commit the remote does not have.

## CI dispatch

If GitHub Actions workflows fail to dispatch on a PR stack, restart the existing runs rather than
pushing a new commit.

## Claims in a PR body

Every limiting claim ("only", "none", "does not exist", "never") needs the command that proved it.
Run it before you write the sentence, and put the count or the path in the body when the claim is
surprising. A claim written from memory is a guess. If a later read shows it was wrong, correct the
body in the same push.

## Checking many PRs at once

For a stack or a batch, read all of them in one call instead of a `gh pr view` loop:
`gh pr list --state open --json number,title,isDraft,mergeStateStatus,baseRefName`. For a stack,
`gh stack view` shows the order. To add a branch to an existing stack: `gh stack unstack`, then
`gh stack init <every branch, bottom to top>`, then `gh stack submit`. Merge with `gh stack merge`
only when I say so. To wait on one PR, use `babysit`, not a poll.
