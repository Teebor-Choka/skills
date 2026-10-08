# Mechanical fixes per failure class

Use the repo's own tooling; look in its README, CI workflow, `justfile`, `Makefile`, or flake
before guessing. Each fix must be reproducible by one command and leave a diff limited to the
expected files.

## fmt

Run the formatter CI runs, not a different one. Common forms: `nix fmt`, `cargo fmt --all`,
`prettier --write .`, `pre-commit run --all-files`. A bump of the formatter itself (for example a
flake input update that changes `nixfmt` or `treefmt` output) is the usual cause on Nix repos.
Commit only the files the formatter changed.

## lint

Apply only fixes the tool marks machine-applicable: `cargo clippy --fix` (review the diff),
`eslint --fix`. A new lint that needs a judgment call (rename, restructure, add an `allow`) is not
mechanical: report it.

## audit

1. Confirm the advisory is new in this PR: run the audit on the base branch. If it also fails there,
   the PR did not cause it; report and do not touch it.
2. If the PR bumped into a vulnerable version, check whether a patched version exists
   (`cargo update -p <crate>`, `npm audit fix` limited to the named package) and apply that one bump.
3. Never edit the ignore list (`audit.toml`, `deny.toml`, `.npmrc` audit level).

## build

- Lockfile out of date: regenerate with the ecosystem command and commit only the lockfile
  (`cargo update -w` or `cargo check`, `npm install --package-lock-only`, `nix flake lock`, `go mod tidy`).
- Compile error caused by a major or minor API change in the bumped dependency: not mechanical.
  Report the error and the changelog link; a human decides.

## test

Report the failing test name and log excerpt. Do not rerun, edit, skip, or delete tests.

## other

Runner outage, expired credentials, network errors, or missing secrets: workflows triggered by
Dependabot see only Dependabot secrets, not Actions secrets ([GitHub docs](https://docs.github.com/en/code-security/dependabot/troubleshooting-dependabot/troubleshooting-dependabot-on-github-actions),
accessed 2026-10-07). Report; do not work around.
