# Maintenance skills

Skills for keeping a project healthy over time, as opposed to writing its code. Portable Agent
Skills (`SKILL.md`) that run on Claude Code, Codex, and OpenCode.

| Skill                                   | What it does                                                                                                                                                    | Reach for it when                                                              |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [project-docs](./project-docs/SKILL.md) | Give any project a standard, enforceable `docs/` (overview, optional spec, ADRs) with diagrams and an AGENTS.md pointer, plus a validator to keep it conformant | "document this project", "standardize our docs", "write the overview and ADRs" |

A project here is any coherent unit of work, a code repo, a subproject, or a non-code effort, not
only a codebase. project-docs authors the documentation (borrowing ADR and spec-test discipline from
the [architect](../engineering/architect/SKILL.md) skill and its voice from
[unslop](../model/tools/unslop/SKILL.md)) and ships the validator that enforces the structure in
pre-commit and CI.
