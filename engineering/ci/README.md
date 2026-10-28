# CI skills

Skills for continuous integration and delivery pipelines. Each is a portable Agent Skill
(`SKILL.md`) that runs unchanged on Claude Code, Codex, and OpenCode — see
[agent-extension-author](../../model/tools/agent-extension-author/SKILL.md) for the cross-agent model.

| Skill                                       | What it does                                                                                                                                                       | Reach for it when                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| [github-actions](./github-actions/SKILL.md) | Harden GitHub Actions workflows and configure Renovate                                                                                                             | editing `.github/workflows/**`, a reusable workflow, or Renovate config |
| [dep-pr-triage](./dep-pr-triage/SKILL.md)   | Triage open Dependabot and Renovate PRs across orgs: classify each red check, apply the mechanical fix on the PR branch, push, re-check. Never merges or approves. |
