---
name: agents-dir
description: >
  The `.agents/` directory contract: the physical documents that define a project's process
  and how they evolve. Use when asked where the policy, procedure, charter or iteration
  records live, to set up or standardize `.agents/`, to add or change a process document, to
  check that a change to the process is documented, or to find the revision a run was
  frozen at. Each document answers one question, a change to any of them is a change request,
  and the validator refuses one with no iteration record. Not for the `docs/` tree (use
  project-docs), not for what is inside a procedure (use procedure) or a policy (use policy).
license: MIT
compatibility: any
metadata:
  version: "1.3.0"
---

# agents-dir: the process is a set of documents

A project's process is defined by documents in its own git repo, under `.agents/`. The runtime
reads them and never keeps a private copy. A change to the process is a change to these files, so
review, CI, branch protection, blame and revert already apply.

## Layout

| Path                        | The one question it answers                                                                | Written by                                    |
| --------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `policy.md`                 | How strict, how often, which procedure? (settings)                                         | a change request                              |
| `procedures/<name>.md`      | What runs, in what order, by whom? (structure)                                             | a change request                              |
| `charter.md`                | Who is the owner, where are they reached, which procedure runs on which trigger? (binding) | a change request                              |
| `iterations/NNNN-<slug>.md` | What changed, why, and what did it do?                                                     | with each change, closed when its window ends |
| `runs/<id>/`                | What happened? (event log, checkpoints)                                                    | the runtime, git-ignored, never a source      |

Names this skill does not own, such as `.agents/skills/`, are left alone.

## Rules

1. **Each document is valid on its own.** The policy loads. Each procedure passes the `procedure`
   validator in strict mode and is named after its file. The charter names an owner with a non-empty
   `channel` and `answer-path`, names only procedures that exist, and holds no secret: a key, token
   or password belongs outside the repo.
2. **Names resolve.** The policy's `procedure` key and each of the charter's `triggers` name a file in
   `procedures/`.
3. **Iterations are numbered, contiguous and append-only.** A record is named `NNNN-<slug>.md`. It has a
   `change` map (`reason`, `metrics`, `direction`, `window`), a `touches` list of the process
   documents it changed, an `outcome`, and once merged a `revision` (a commit id). A record may be
   updated when its window closes. It may not be deleted or renamed.
4. **`runs/` is git-ignored.** Run output is never a source.
5. **No change without a record.** A change to `policy.md`, `charter.md` or a procedure must add an
   iteration record in the same change, and each changed document must be in the `touches` of a record
   added in it. Updating an old record does not count.

```
python3 scripts/agents_dir.py REPO               # the files as they are
python3 scripts/agents_dir.py REPO --base main   # also the change since main (run it in CI)
```

It exits 1 and prints each error. An unknown `--base` is an error, never a pass.

## How a change flows

A change to the process is a change request that edits the documents and adds its iteration record.
The `procedure` validator and this one run in CI. Your merge is the approval, so no agent can write a
snapshot. A snapshot is the revision `process_revision(repo)` returns: the commit that last changed a
process document. A run freezes that revision when it starts. A rollback is a revert commit, and
history is never rewritten. When a change's window closes, its record is updated with the outcome.

## Resolving a run: project over user, and what a parent passes

A run reads its documents from two places. For each document the project's `.agents/` wins, then the
user's `$XDG_CONFIG_HOME/agents/` (default `~/.config/agents/`; no dot under XDG). With neither, the
tool does nothing: `resolve` returns `None`, `start_run` returns `None` and the command prints "nothing
to do" and exits 0. A policy and a charter with no procedure also leave nothing to run.

| Document               | Rule                                                           |
| ---------------------- | -------------------------------------------------------------- |
| `policy.md`            | layered per key, the project over the user                     |
| `procedures/<name>.md` | the project's file if it has one of that name, else the user's |
| `charter.md`           | the project's if it has one, else the user's                   |

A parent that starts a worker can also pass the documents directly, as `inline` (`policy`, `charter`,
`procedures`; the command takes `--inline FILE.json`). Inline is the top layer: it wins over the
project and the user, is held to every guard below, and is pinned in the revision by hash. Nothing in
it is read from disk, so a worker needs no `.agents/` of its own.

The split is deliberate: a global procedure says how, and each project's `policy.md` supplies the
specifics the procedure declares (see the `procedure` skill, "Policy bindings"). The procedure that
runs is the explicit name, else the policy's `procedure` key, else the charter's, else the only one
available. Several and no choice is an error.

A run is refused unless:

- the procedure is valid in strict mode and named after its file;
- every policy key the procedure declares is set (bindings are returned for exactly those keys);
- the policy values the runtime checks are usable (`max-agents`, `max-depth`, `regression-threshold`,
  `safety-metrics`), since a file holds text and the runtime needs numbers;
- the project's process documents have no uncommitted changes, unless a dirty tree is allowed, and git
  can report their state (a failing `git status` is an error, not a clean tree).

The run pins `revision`: the project commit that last changed a process document, and a hash of the
user documents it used, plus a hash of any inline documents. That is what a snapshot refers to.

### A cloned repo must not override a trusted setup

"Project wins" would let whoever wrote a repo replace your procedure, charter and policy. The override
is guarded:

- **Locked keys.** List keys in `locked: [mode, vcs.remote]` in the user's policy. The resolved policy
  must hold, for each, what the user's layer alone gives, so a changed value, a key the user left
  unset, a scalar over a map and a sibling overlay that replaces a nested map are all errors. Only the
  user's list counts, and a `locked` that is not a list of dotted keys is an error. A lock also covers
  the key set for one skill (`<skill>: {key: ..}`) or one file (`files:`).
- **A weaker procedure.** A project or inline procedure is compared with the user's procedure of the
  same name and with the one the user runs (a rename, or a swap for another of the user's, does not
  shed a floor); inline is also compared with the project's. When the user has several procedures and
  names none (`procedure` in the user's policy), a project or inline procedure with no same-name
  counterpart is refused, since the floor to keep is unknown. A procedure that fails validation is
  refused before any comparison. It may not drop, rewire or strip a floor stage, remove its review angles, rewire a
  stage around it, a floor stage's `on-fail`, or move the ladder, a loop (its `stages`, `exit`, `on-exhausted`) or a KPI. A key it leaves out counts as changed. A
  user baseline that is itself invalid is an error.
- **A different owner.** A project or inline charter may not name a different `owner` than a lower one,
  and an empty charter does not drop it. A user charter whose `owner` is not a map is an error.
- **Hostile files.** In the project, a symlinked document, `.agents/` or `.agents/procedures/`, an
  oversized (over 256 KB) or unreadable document is an error. The user's own layer may be symlinked
  (home-manager, stow). Inline input is capped at 64 procedures, 256 KB a document and 2 MB a file. A procedure name must be lowercase letters, digits and
  dashes, so it cannot name a path. Git runs without the repo's fsmonitor, inherited `GIT_*`
  variables or system config. The dirty check hashes each process document and compares it with
  `HEAD` (no `git status`, so no repo filter runs); an untracked or git-ignored document counts as
  changed.

```
python3 scripts/resolver.py PROJECT [--procedure NAME] [--allow-dirty] [--inline FILE.json]
```

The command prints the procedure, revision, sources and bindings, never the policy or the procedure
text, and exits 1 on any error. `start_run(project, trust="signed")` freezes the result into a run.

## What this does not do

- It does not decide who may merge. Branch protection or `CODEOWNERS` on `.agents/` does. This checks
  that the documents are consistent and that a change is documented, not that the right person
  approved it.
- It does not check that an iteration record's metrics exist in the procedure it touches, or that its
  `outcome` is true. The runtime owns the outcome.
- It does not protect a repo whose `.agents/` is edited without CI. Wire it into CI and pre-commit.
- Inline documents are trusted as the parent's
  authority only as far as the user's locks and floor allow; the resolver cannot tell a parent from an
  attacker who controls the call, so the caller must be trusted.
- With no git repo (a tarball), or no `git` on the path, a project's documents are used unpinned with
  no dirty check; `revision.project` is `None`. Run from a repo when the pin matters.
- The user policy is read more than once (parse, hash, load), so a file changed during resolution can
  differ from the hash in `revision.user`.
- A user who does not lock `regression-threshold` or `safety-metrics` lets a project weaken the
  rollback checks (a huge threshold, an empty list). Lock them.
- Locking covers policy keys, the owner and the floor. A project can still change policy values the
  user did not lock, for example `mode`, so lock what matters.
- It reads the policy loader's layering, which treats a missing user policy as no policy.
- It does not run anything: the executor does that.
