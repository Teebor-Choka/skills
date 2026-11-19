# Enforcement

The validator is the mechanical half: it guarantees the structure exists and conforms, so the
authoring half can focus on content. It checks structure, never content quality or currency (see
the end of `contract.md` for the boundary).

## Running it

```sh
python3 scripts/validate_docs.py <project>          # one project
python3 scripts/validate_docs.py --all <root>    # every repo under root; prints the work queue
python3 scripts/validate_docs.py <project> --json   # machine-readable findings
```

Pure Python 3 standard library, no dependencies to install. Exit code is 0 only when everything
checked passes. Any finding, including one labelled `warning` (such as `undocumented`), makes it
exit 1; a usage error or an unexpected failure exits 2. It drops straight into a hook or a CI step.

Where the target has `docs/components/`, `components.py` must sit beside `validate_docs.py`; the
validator exits 2 naming it when it does not. `render_docs.py` loads `components.py` and
`validate_docs.py` the same way. Keep the three scripts in one directory: `install_hook.sh` refuses
to run unless all three sit beside it, and the Nix snippet vendors all three.

The renderer has its own modes, all in "Generated files" in `contract.md`:

```sh
python3 scripts/render_docs.py <project>               # write docs/generated/*
python3 scripts/render_docs.py <project> --check       # exit 1 on drift; also runs the update trigger
python3 scripts/render_docs.py <project> --check --no-trigger   # drift only; needs no .git
```

## Wiring it into a target repo

`scripts/install_hook.sh <target-project>` wires the validator to run on commit. It is
**origin-aware**: it detects how the target already manages hooks and joins that mechanism rather
than overwriting it, because projects differ and clobbering someone's hook setup is worse than no
hook.

- **pre-commit framework** (the target has a `.pre-commit-config.yaml`): it prints the local-hook
  stanza for you to add under `repos:`, and never edits the file. A blind append would corrupt the
  YAML whenever `repos:` is not the last top-level key, so placing it is left to you.
- **otherwise** (any git repo): it installs the hook at the directory git actually runs hooks from
  (`git rev-parse --git-path hooks`, which already resolves `core.hooksPath` and a linked worktree's
  shared common dir), inserting the check after the shebang so an existing hook that ends in
  `exit 0` cannot strand it.

The hook resolves the repo at commit time (`git rev-parse --show-toplevel`) and validates the
**staged** content, exported from the index to a temp dir, so linked worktrees and unstaged edits
behave. If the validator file is gone (for example a garbage-collected Nix store path), the hook
fails and says to re-run `install_hook.sh`. It never overwrites a symlinked hook, and never writes
into a `core.hooksPath` outside the target repo (it may be shared); in both cases it prints the
block to add by hand.

It is idempotent: re-running does not duplicate the hook.

**Pre-push render check.** The same run installs a `pre-push` hook beside the `pre-commit` one (same
rules for symlinks, `core.hooksPath` and linked worktrees). It runs `validate_docs.py` and then
`render_docs.py --check` on the working tree, because the update trigger needs git history and the
manifests. It exits 1 without checking when `docs/` has uncommitted changes, since those could hide
drift in the commits being pushed. A repo without `docs/` passes. The pre-commit framework gets a
second printed stanza, `project-docs-render` with `stages: [pre-push]`, and nothing is edited.

## Nix repos gate in the flake

A repo with a `flake.nix` usually runs its checks through `nix flake check`, not only a git hook, so
a hook alone would be invisible to that gate. When the target has a flake, `install_hook.sh` prints
a ready-to-paste snippet with two derivations: `checks.<system>.project-docs` (the validator) and
`checks.<system>.project-docs-render` (`render_docs.py --check --no-trigger`). Copy `validate_docs.py`,
`components.py` and `render_docs.py` into one in-tree directory (`ci/`) and reference it as a
directory (`${./ci}/render_docs.py`), not as single files: a lone file lands in the store without its
siblings and the import fails. The Nix sandbox has no `.git`, so the flake check covers drift only;
the update trigger runs in the pre-push hook and in a CI step with a checkout (pass `--base` with the
PR base SHA). The git hook and the flake check are complementary: the hook catches it before push,
the flake check catches it in CI and for anyone who skips hooks.

## Formatters

A formatter that rewrites `docs/generated/*` makes `--check` fail on every run. `install_hook.sh`
prints the exclude for each tool; add it wherever the repo formats:

- `.prettierignore`: `docs/generated/**`
- `treefmt.toml`: `[global]` `excludes = ["docs/generated/**"]`
- treefmt-nix: `settings.global.excludes = [ "docs/generated/**" ];`

## Pull requests

`AGENTS.pointer.md` carries the mandatory line: when any `docs/**/*.md` changes, run `render_docs.py`,
commit `docs/generated/*`, and paste `render_docs.py --pr-summary` into the PR description. The
pre-push hook and CI enforce the render; pasting the summary is the author's step. Two PRs that both
touch docs conflict on the generated files: rebase and re-render, never hand-merge them.

## CI

In a plain CI job, run `python3 scripts/validate_docs.py --all .` (or per repo) as a step, then
`python3 scripts/render_docs.py . --check --base <PR base SHA>` for each repo that has `docs/`. It needs
only Python 3 (3.11 or later when a component manifest is TOML). For a monorepo-of-repos, `--all` gives one pass over everything and a nonzero exit if
any repo drifts.

## What it cannot do

It confirms presence and shape: the tree, frontmatter, ADR sections, the decisions index in both
directions, the AGENTS.md pointer, that the mandatory mermaid blocks exist, and that each optional
`docs/views/*.html` is self-contained, themed, and as current as its source. It cannot tell
whether a diagram is accurate, whether prose is actually terse, or whether an ADR is still true.
Those are caught by writing it right (the authoring flow) and by the optional staleness review knob
(a review that flags "the code changed but its ADR, spec, or diagram did not"), not by this script.
