# Bindings

The loop is forge-neutral. These nouns are abstract in the skill body; one binding maps them
to a concrete toolchain. The process never names the tool — this file does.

Which binding is active is read from policy: **`work.tracker`** in `.agents/policy`
(`policy_loader.py <repo> --get work.tracker`). It selects the binding below — `github`,
`gitlab`, `jira`, `beads`, … Unset, and inside a GitHub repo with `gh`, it defaults to `github`;
otherwise `none` (no tracker — the loop runs locally, nothing is filed or integrated through a
forge). The same key is read by the design skill (policy `design`), so packages and items land in one place.

| Abstract verb/noun | Meaning                                                      |
| ------------------ | ------------------------------------------------------------ |
| work item          | one unit of work, with acceptance criteria and dependencies  |
| tracker            | where work items live                                        |
| change request     | the reviewable proposed change linked to its work item       |
| checks             | the automated gates on a change request (CI, the review bot) |
| integrate          | land the change; close the work item                         |

## GitHub binding (`work.tracker: github`, the default)

| Verb                 | Command                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| take work item       | `gh issue view <N>`; claim by comment + label in `mode: team`                                     |
| file new work item   | `gh issue create --type <type> --title ... --body ...` (link the parent; type per `git:workflow`) |
| open change request  | `gh pr create --title ... --body "...Closes #N"`                                                  |
| mark ready           | `gh pr ready <N>` (the watcher below does this when it starts)                                    |
| checks state         | `gh pr checks <N>`                                                                                |
| watch change request | `git:workflow`'s `babysit [branch]`, in the background, per its "Babysitting a PR" section        |
| external review      | CodeRabbit (or the repo's review app) posts on the PR                                             |
| integrate            | `gh pr merge <N> --squash` per the merge policy                                                   |

Dependencies: a `Blocked by #N` line in the item body; the item is workable only once every
blocker is integrated.

### Gate state query

The hook (`hooks/gate.sh`) does not block a boundary blindly; it asks this binding whether the
boundary's condition actually holds, via `scripts/forge-state.sh <repo> <commit|ready|integrate>
[pr-ref]`:

| Boundary            | Checked by the GitHub binding                                                      |
| ------------------- | ---------------------------------------------------------------------------------- |
| `integrate` (merge) | the PR's CI is all green (`gh pr checks`) AND `reviewDecision == APPROVED`         |
| `ready`             | nothing: always indeterminate (`2`); CI and review are the feedback ready asks for |
| `commit` (tdd)      | the branch carries a test-touching commit (the red-first git artifact)             |

Exit codes: `0` met, `1` genuinely unmet, `2` indeterminate (no `gh`, no PR yet, offline).
`gate.sh` passes `--ok` to `policy-gate` on `0`; on `1` it lets policy-gate block/warn by mode;
on `2` it blocks `integrate` (never merge unverified) but allows `commit`/`ready` (`commit` is not
machine-checkable before the PR exists; `ready` is the agent's own call that the implementation is
complete, so the local policy gate decides it).

## Local binding (`work.tracker: none`)

For a repo with no forge to query: a local bare remote, or no remote at all. Nothing is filed
or reviewed through a forge, so each verb maps to plain git and the repo's own checks.

| Verb                 | Local mapping                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------- |
| take work item       | the request in the session, or a file/note the repo keeps; state its acceptance criteria |
| open change request  | the branch itself (`<nick>/<type>/<component>/<description>`); no PR                     |
| checks state         | the repo's own commands (its AGENTS.md lists them), run locally and read in full         |
| external review      | none; the isolated reviewer (step 5) and the human are the review                        |
| watch change request | none; there is no CI to babysit                                                          |
| integrate            | `git merge --ff-only` (or the repo's rule) into the default branch, then push            |

Gate behaviour. `forge-state.sh` has no forge, so `integrate` returns `2` (indeterminate) and
`gate.sh` blocks a `git merge` in `mode: team`. After the local checks pass and the human approves,
run the merge as `SWE_GATE_OK=1 git merge ...`. In `mode: single` the gate warns and allows. A repo
that will never have a forge should set `mode: single` in its `.agents/policy.md` instead of
overriding every merge.

## Selecting the binding

Set **`work.tracker`** in the repo's `.agents/policy`; it names the binding — the skill body and
`policy-gate` do not change. Swap this file's commands (and `scripts/forge-state.sh` with them) for
the named toolchain:

- **`github`** (the default): the table above.
- **`none`**: the local binding above.
- **`beads`** (`bd`): work items and their dependency graph live in `bd`; change requests still go
  to the forge. `bd` gives the real dependency graph GitHub issues lack.
- **`gitlab`**: merge request (`glab mr create`) for change request; `glab ci status` for checks,
  with a `forge-state.sh` that reads `glab` instead of `gh`.

One `work.tracker` per repo (the same key the design skill reads). The acceptance-criteria,
dependency, and claim rules are the same whichever tool backs them.
