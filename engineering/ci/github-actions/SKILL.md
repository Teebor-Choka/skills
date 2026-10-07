---
name: github-actions
description: >
  Harden GitHub Actions workflows and configure Renovate correctly. Use whenever a repository
  has a .github/workflows directory, or you are creating, editing, or reviewing a workflow
  YAML, a reusable/called workflow, or Renovate config (renovate.json or .github/renovate.json).
  Covers template-injection prevention (no expression interpolation inside run blocks), pinning
  actions to a commit SHA, avoiding secrets inherit, job-scoped permissions, reusable-workflow
  naming, running zizmor after edits, and Renovate root-config precedence, security-update
  matching, and ignorePaths for vendored manifests. Trigger even when the workflow edit is a
  small part of a larger change. Do not use for non-GitHub CI systems, or for general CI
  concepts unrelated to GitHub Actions and Renovate.
license: MIT
compatibility: any
---

# GitHub Actions

Security and configuration standards for GitHub Actions workflows and Renovate. Apply these
whenever a repo has `.github/workflows/`, or you touch a workflow file or Renovate config.

## Workflow hardening

- **Template injection.** Never interpolate a `${{ }}` expression directly inside a `run:`
  block — an attacker-controlled value (a PR title, a branch name) becomes shell code. Move it
  to a step-level `env:` block and reference the shell variable instead. Expressions in `with:`
  blocks (action inputs) are safe.
- **Pin actions to a commit SHA** with the version in a trailing comment, e.g.
  `uses: foo/bar@<sha> # v2`. When resolving a tag to a SHA, dereference annotated tags to the
  underlying commit — the `git/ref/tags/<tag>` API may return a tag object, not a commit.
- **No `secrets: inherit`.** Declare secrets in the reusable workflow's `workflow_call` block
  and pass them explicitly from the caller, so each workflow's secret surface is visible.
- **Scope permissions per job**, not at workflow level, and grant only what the job needs
  (e.g. `contents: read`). Avoid broad workflow-level `write`.
- **Reusable-workflow naming.** The caller's `name:` becomes the prefix in the GitHub UI (e.g.
  `Test / Unit`), so inner jobs should use short names that do not repeat the group.
- **Run `zizmor` after editing any workflow file**: `zizmor --format plain .github/workflows/`,
  and fix all findings before committing. If `zizmor` is not on `PATH` (not in the nix devshell,
  say), skip it rather than installing it.

## Merge queue and branch rulesets

- **A required check must also run on `merge_group`.** If a status check is required for merge but
  its workflow doesn't trigger on the `merge_group` event, the queue waits forever for a status
  that never arrives — a deadlock. A conditionally-skipped Actions job still reports green, so it
  satisfies the requirement without running; guard a heavy job you want to skip in the queue with
  an `if:` condition rather than dropping `merge_group` from the triggers. External checks (e.g.
  Codecov) can't skip-green, so they must genuinely run on `merge_group`.
- **Add the merge queue as a separate overlay ruleset** scoped to the default branch, instead of
  folding it into an existing ruleset — it keeps the queue's config from being rewritten with
  unrelated rule changes.
- **The `integrations/github` Terraform provider (as of 6.13.0) can't model the
  `require_extra_approval_for_unattributed_changes` pull-request ruleset parameter** and silently
  drops it on every rewrite, which disables the control. Workaround: a `terraform_data` resource
  re-runs a script that restores the field idempotently after each write, and don't let Terraform
  rewrite rulesets that are managed by hand.
- **To audit which repos lack a ruleset or have security updates off**, use the read-only `gh api`
  recipe in [references/org-audit.md](references/org-audit.md); fix drift in Terraform, not by hand.

## Codecov

- **Authenticate the Codecov upload via GitHub OIDC** — set `permissions: id-token: write` on the
  job and drop the static `CODECOV_TOKEN`. Because it's a workflow permission rather than a
  repository secret, the upload also works on Dependabot PRs (which run without access to secrets).
- **Pushing a workflow file needs the `workflow` OAuth scope.** If a `git push` that touches
  `.github/workflows/` is rejected, refresh the token: `gh auth refresh -h github.com -s workflow`.

## Renovate

- **Root config precedence.** Before adding a `renovate.json` at the repo root, check for an
  existing `.github/renovate.json` — the root file silently takes precedence. Merge the
  `.github/renovate.json` settings into the root file, then delete `.github/renovate.json`.
- **Keep security updates unclamped.** Security/vulnerability fixes ship as patch, minor, or major
  bumps, so a `matchUpdateTypes` filter that drops non-patch updates silently misses them. Configure
  vulnerability handling through Renovate's `vulnerabilityAlerts` object — there is no `security`
  value for `matchCategories` (it takes ecosystem categories), so a rule keyed on it never matches.
- **`ignorePaths` for vendored manifests.** If a repo vendors third-party files with their own
  manifests (e.g. `vendor/` with `package.json` or `Cargo.toml`), add
  `"ignorePaths": ["vendor/**"]` so Renovate does not open PRs against them.
