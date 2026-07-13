# Skills — Public

Public AI agent skills for [Claude Code](https://claude.ai/code) and compatible agent hosts.

## Skills

| Skill                                                     | Description                                                                       |
| --------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [forge-idea](./tools/forge-idea/SKILL.md)                 | Forge rough ideas into viable ones through cooperative, research-driven iteration |
| [llm-wiki](./tools/llm-wiki/SKILL.md)                     | Create, maintain, and query a personal knowledge wiki designed for LLM navigation |
| [rust-engineer](./engineering/swe/rust-engineer/SKILL.md) | Enforce Rust code quality and guidelines throughout Rust development              |

## Install

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills
```

Or install a single skill:

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills --plugin forge-idea
```

## Repository layout

Skills are grouped into thematic categories for source organization. The grouping is invisible to the agent host — skills are discovered by their `name` field in `SKILL.md`.

```
tools/
  forge-idea/           # skill: forge-idea
  llm-wiki/             # skill: llm-wiki
engineering/swe/
  rust-engineer/        # skill: rust-engineer
```

Each skill is a self-contained directory:

```
<skill-name>/
├── SKILL.md        # Instructions + YAML frontmatter (name, description)
├── references/     # Reference files loaded on demand
└── assets/         # Copyable artifacts (templates, CI scripts, …)
```

## License

MIT — see [LICENSE](./LICENSE).
