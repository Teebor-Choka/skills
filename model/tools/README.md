# Model & tooling skills

Skills about the model's own output and about building agent tooling itself. Both are portable
Agent Skills (`SKILL.md`) that run on Claude Code, Codex, and OpenCode.

| Skill                                     | What it does                                                                                                               | Reach for it when                                                                                  |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [unslop](./unslop/SKILL.md)               | Edit prose to remove AI tells and restore a plain, human voice — structure first, then surface                             | before shipping docs/READMEs/commits/PRs; "make this sound less like AI"                           |
| [skill-creator](./skill-creator/SKILL.md) | Author, port, and harden Agent Skills across Claude Code, Codex, and OpenCode — triggering, workflows, and an eval harness | "make a skill", "package this as a skill", "why isn't my skill firing", target more than one agent |

[skill-creator](./skill-creator/SKILL.md) is the reference for the cross-agent model the rest
of this repo follows: one portable `SKILL.md` core plus per-agent adapters for triggering and
orchestration. Its `scripts/validate_skill.py` lints the portable contract and is used across
these skills.
