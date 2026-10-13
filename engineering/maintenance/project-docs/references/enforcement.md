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
checked passes, nonzero otherwise, so it drops straight into a hook or a CI step.

## Wiring it into a target repo

`scripts/install_hook.sh <target-repo>` wires the validator to run on commit. It is
**origin-aware**: it detects how the target repo already manages hooks and joins that mechanism
rather than overwriting it, because repos differ and clobbering someone's hook setup is worse than
no hook.

- **pre-commit framework** (the target has a `.pre-commit-config.yaml`): it prints the local-hook
  stanza to add, and only writes it with `--write`. It never silently rewrites that file.
- **plain hooks** (`git config core.hooksPath` is set): it adds a `pre-commit` hook in that
  directory calling the validator.
- **neither**: it installs `.git/hooks/pre-commit`, appending if one already exists, never
  overwriting blind.

It is idempotent: re-running does not duplicate the hook.

## Nix repos gate in the flake

A repo with a `flake.nix` usually runs its checks through `nix flake check`, not only a git hook, so
a hook alone would be invisible to that gate. When the target has a flake, `install_hook.sh` prints
a ready-to-paste snippet adding the validator as a `checks.<system>.project-docs` derivation. Add it so
the docs check runs in the same gate as the repo's other checks (treefmt, clippy, tests). The git
hook and the flake check are complementary: the hook catches it before commit, the flake check
catches it in CI and for anyone who skips hooks.

## CI

In a plain CI job, run `python3 scripts/validate_docs.py --all .` (or per repo) as a step. It needs
only Python 3. For a monorepo-of-repos, `--all` gives one pass over everything and a nonzero exit if
any repo drifts.

## What it cannot do

It confirms presence and shape: the tree, frontmatter, ADR sections, the decisions index in both
directions, the AGENTS.md pointer, and that the mandatory mermaid blocks exist. It cannot tell
whether a diagram is accurate, whether prose is actually terse, or whether an ADR is still true.
Those are caught by writing it right (the authoring flow) and by the optional staleness review knob
(a review that flags "the code changed but its ADR, spec, or diagram did not"), not by this script.
