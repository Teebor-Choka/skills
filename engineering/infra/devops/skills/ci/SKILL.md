---
name: ci
description: >
  Harden CI: GitHub Actions and Renovate. Load before editing any .github/workflows/*.yml, a
  reusable workflow, renovate.json or dependabot config: SHA pins, no template injection,
  least permissions, zizmor. Not for other CI systems.
license: MIT
compatibility: any
---

# ci

Standards for the CI a repo runs and the bots that update its dependencies. This skill routes; the
rules live in one reference per CI system. Read the matching reference in full before the first
edit, and apply it even when the CI change is a small part of a larger one.

| You touch                                                                                | Read                                                                                |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `.github/workflows/*.yml`, a reusable workflow, a merge queue or branch ruleset, Codecov | [references/github-actions/guide.md](references/github-actions/guide.md)            |
| `renovate.json`, `.github/renovate.json`, dependabot config                              | [references/github-actions/guide.md](references/github-actions/guide.md) (Renovate) |
| shellcheck, actionlint and zizmor as pre-commit hooks                                    | [references/github-actions/lint-hooks.md](references/github-actions/lint-hooks.md)  |

zizmor is mandatory on every workflow edit, and a workflow with no zizmor report is reported as
unvalidated. The guide holds the fallback order and the read-only rule for a `security` stage 4
handover.
