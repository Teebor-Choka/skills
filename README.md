# Skills — Public

Public AI agent skills for [Claude Code](https://claude.ai/code) and compatible agent hosts.

## Skills

Grouped by source directory (see [Repository layout](#repository-layout)).

### tools

| Skill                                     | Description                                                                       |
| ----------------------------------------- | --------------------------------------------------------------------------------- |
| [forge-idea](./tools/forge-idea/SKILL.md) | Forge rough ideas into viable ones through cooperative, research-driven iteration |
| [llm-wiki](./tools/llm-wiki/SKILL.md)     | Create, maintain, and query a personal knowledge wiki designed for LLM navigation |
| [hopr-debug](./tools/hopr-debug/SKILL.md) | HOPR mixnet debugging aid — loads ground-truth protocol knowledge (RFC-0001–0014) |

### model/tools

| Skill                                   | Description                                                      |
| --------------------------------------- | ---------------------------------------------------------------- |
| [unslop](./model/tools/unslop/SKILL.md) | Edit writing to remove AI tells and restore a plain, human voice |

### engineering/swe

| Skill                                                     | Description                                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [rust-engineer](./engineering/swe/rust-engineer/SKILL.md) | Enforce Rust code quality and guidelines throughout Rust development                  |
| [code-quality](./engineering/swe/code-quality/SKILL.md)   | Audit code for risk via complexity, coverage, structural metrics, and comment quality |

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
  hopr-debug/           # skill: hopr-debug
model/tools/
  unslop/               # skill: unslop
engineering/swe/
  rust-engineer/        # skill: rust-engineer
  code-quality/         # skill: code-quality — workflows: measure, comments
```

Each skill is a self-contained directory:

```
<skill-name>/
├── SKILL.md        # Instructions + YAML frontmatter (name, description)
├── references/     # Reference files loaded on demand
└── assets/         # Copyable artifacts (templates, CI scripts, …)
```

## Acknowledgements

The [`unslop`](./model/tools/unslop/SKILL.md) skill was not written from scratch. It was built by pooling the strongest open "unslop" (de-AI-writing) agent skills on GitHub, deduplicating their rules and word lists, and folding in the research they cite, then restructuring the result around a structure-first pass (surface word-swaps alone barely move AI detection). Full attribution with links is in [model/tools/unslop/references/sources.md](./model/tools/unslop/references/sources.md).

With thanks to the authors of the MIT-licensed skills we pooled from: [theclaymethod/unslop](https://github.com/theclaymethod/unslop), [mshumer/unslop](https://github.com/mshumer/unslop), [MohamedAbdallah-14/unslop](https://github.com/MohamedAbdallah-14/unslop), [asavvin-pixel/unslop](https://github.com/asavvin-pixel/unslop), [woerndl/unsloppify](https://github.com/woerndl/unsloppify), [mnapoli/skills](https://github.com/mnapoli/skills), and the `cursor/plugins` `pstack` base (surfaced via [ui-skills.com](https://www.ui-skills.com/skills/cursor/unslop)).

And to the research that shaped the structural pass: Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (CC BY-SA 4.0, used as a factual reference), the [StoryScope](https://github.com/jenna-russell/storyscope) paper (arXiv:2604.03136), the UMD / Google DeepMind cliché-removal study, [Berens & Kobak's](https://github.com/berenslab/llm-excess-vocab) excess-vocabulary analysis, and the [Google developer style guide](https://developers.google.com/style/word-list).

## License

MIT — see [LICENSE](./LICENSE).
