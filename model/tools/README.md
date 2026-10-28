# Model & tooling skills

Skills about the model's own output and about building agent tooling itself. Both are portable
Agent Skills (`SKILL.md`) that run on Claude Code, Codex, and OpenCode.

| Skill                                                       | What it does                                                                                                                                         | Reach for it when                                                                                            |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [prose-craft](./prose-craft/SKILL.md)                       | Compose or revise prose for clarity and concision, grounded in Strunk & White and Pinker: structure, then sentences, then words                      | drafting or improving any connected prose; "tighten this", "make this clearer", "why does this read badly"   |
| [unslop](./unslop/SKILL.md)                                 | Edit prose to remove AI tells and restore a plain, human voice — structure first, then surface                                                       | before shipping docs/READMEs/commits/PRs; "make this sound less like AI"                                     |
| [agent-extension-author](./agent-extension-author/SKILL.md) | Author, port, and harden Agent Skills across Claude Code, Codex, OpenCode, and oh-my-pi — triggering, workflows, native plugins, and an eval harness | "make a skill", "package this as a skill or plugin", "why isn't my skill firing", target more than one agent |
| [session-retrospective](./session-retrospective/SKILL.md)   | Mine agent sessions for the moments the agent struggled, then propose fixes to the skills, environment, and workflows it used.                       |

[agent-extension-author](./agent-extension-author/SKILL.md) is the reference for the cross-agent model the rest
of this repo follows: one portable `SKILL.md` core plus per-agent adapters for triggering and
orchestration. Its `scripts/validate_skill.py` lints the portable contract and is used across
these skills.
