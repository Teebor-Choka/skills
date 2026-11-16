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
  version: "1.0.0"
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

## What this does not do

- It does not decide who may merge. Branch protection or `CODEOWNERS` on `.agents/` does. This checks
  that the documents are consistent and that a change is documented, not that the right person
  approved it.
- It does not load a procedure into a run, or layer a global file under a local one. That is the
  resolver, which is not built yet.
- It does not check that an iteration record's metrics exist in the procedure it touches, or that its
  `outcome` is true. The runtime owns the outcome.
- It does not protect a repo whose `.agents/` is edited without CI. Wire it into CI and pre-commit.
