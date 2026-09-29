# Skills — Public

Public AI agent skills for [Claude Code](https://claude.ai/code) and compatible agent hosts.

## Skills

Grouped by source directory (see [Repository layout](#repository-layout)). Every skill is a
portable Agent Skill (`SKILL.md`) that runs unchanged on **Claude Code**, **Codex**, and
**OpenCode**; the [skill-creator](./model/tools/skill-creator/SKILL.md) skill documents that
cross-agent model. Each category has its own README with fuller blurbs.

### tools — [details](./tools/README.md)

| Skill                                     | Description                                                                                           |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [forge-idea](./tools/forge-idea/SKILL.md) | Forge a rough idea into a viable one by fanning out parallel agents to stress-test and prune branches |
| [llm-wiki](./tools/llm-wiki/SKILL.md)     | Build, grow, and query a linked Markdown knowledge wiki an LLM can navigate                           |

### model/tools — [details](./model/tools/README.md)

| Skill                                                 | Description                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------------- |
| [prose-craft](./model/tools/prose-craft/SKILL.md)     | Compose or revise clear, well-architected prose (Strunk & White + Pinker) |
| [unslop](./model/tools/unslop/SKILL.md)               | Edit prose to remove AI tells and restore a plain, human voice            |
| [skill-creator](./model/tools/skill-creator/SKILL.md) | Author, port, and harden skills across Claude Code, Codex, and OpenCode   |

### engineering — [details](./engineering/README.md)

| Skill                                         | Description                                                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [architect](./engineering/architect/SKILL.md) | Turn a fuzzy systems/infra requirement into a self-contained, agent-executable work package, then execute it |

### engineering/swe — [details](./engineering/swe/README.md)

| Skill                                                     | Description                                                                                   |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [rust-engineer](./engineering/swe/rust-engineer/SKILL.md) | Enforce Rust house guidelines while writing or reviewing Rust                                 |
| [code-quality](./engineering/swe/code-quality/SKILL.md)   | Audit code risk from complexity/coverage/duplication metrics + comment quality (reports only) |

### engineering/ci — [details](./engineering/ci/README.md)

| Skill                                                      | Description                                            |
| ---------------------------------------------------------- | ------------------------------------------------------ |
| [github-actions](./engineering/ci/github-actions/SKILL.md) | Harden GitHub Actions workflows and configure Renovate |

### environment — [details](./environment/README.md)

| Skill                             | Description                                                                        |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| [nix](./environment/nix/SKILL.md) | Work correctly in Nix + direnv dev repos — nix fmt, build traps, pre-commit tuning |

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
model/tools/
  unslop/               # skill: unslop
  skill-creator/        # skill: skill-creator — references/platforms + validate_skill.py
engineering/
  architect/            # skill: architect — scaffold.py + lint.py, references, adapters
engineering/swe/
  rust-engineer/        # skill: rust-engineer
  code-quality/         # skill: code-quality — workflows: measure, comments
engineering/ci/
  github-actions/       # skill: github-actions — Actions hardening + Renovate
environment/
  nix/                  # skill: nix — Nix + direnv dev workflow
```

Each skill is a self-contained directory:

```
<skill-name>/
├── SKILL.md        # Instructions + YAML frontmatter (name, description)
├── references/     # Reference files loaded on demand
└── assets/         # Copyable artifacts (templates, CI scripts, …)
```

## Acknowledgements

### architect

The [`architect`](./engineering/architect/SKILL.md) skill was written from scratch, drawing on established architecture literature and document standards for their ideas, methodology, and a few short attributed quotes; it reproduces no substantial text from any of them, and references the one copyleft source (arc42, CC BY-SA) by concept only. With thanks to John Ousterhout (_A Philosophy of Software Design_); Mark Richards & Neal Ford (_Fundamentals of Software Architecture_, _Building Evolutionary Architectures_, _Software Architecture: The Hard Parts_); Martin Fowler (monolith-first); Michael Nygard (ADRs) and [MADR](https://adr.github.io/madr/); Alistair Mavin ([EARS](https://alistairmavin.com/ears/)); [arc42](https://arc42.org/overview); and Simon Brown ([C4 model](https://c4model.com/)).

Its graph-engineering step ([`references/graph-patterns.md`](./engineering/architect/references/graph-patterns.md)) is grounded in the workflow / parallel / multi-agent-orchestration literature, every citation web-verified and authority-tagged, with the state of the art through 2026 folded in: the van der Aalst Workflow Patterns paper (2003), GPTSwarm (ICML 2024) and AFlow (ICLR 2025) on agents-as-optimizable-graphs, MaAS (ICML 2025) on query-dependent workflow-graph design, the topology-effects work of Shen et al. (EMNLP 2025) with G-Designer and AgentPrune/AGP, the MAST failure taxonomy (Cemri et al. 2025), and the Yue et al. 2026 survey of workflow optimization as agentic computation graphs. Full attribution with links, license notes, and preprint flags is in [engineering/architect/references/sources.md](./engineering/architect/references/sources.md) and [graph-patterns.md](./engineering/architect/references/graph-patterns.md).

Grounding the current state can optionally run through a code graph, single- or multi-repo, via [`codegraph`](https://github.com/colbymchenry/codegraph) (MIT) when available, with a graceful fall back to manual reading otherwise ([`references/code-graphing.md`](./engineering/architect/references/code-graphing.md)).

### unslop

The [`unslop`](./model/tools/unslop/SKILL.md) skill was not written from scratch. It was built by pooling the strongest open "unslop" (de-AI-writing) agent skills on GitHub, deduplicating their rules and word lists, and folding in the research they cite, then restructuring the result around a structure-first pass (surface word-swaps alone barely move AI detection). Full attribution with links is in [model/tools/unslop/references/sources.md](./model/tools/unslop/references/sources.md).

With thanks to the authors of the MIT-licensed skills we pooled from: [theclaymethod/unslop](https://github.com/theclaymethod/unslop), [mshumer/unslop](https://github.com/mshumer/unslop), [MohamedAbdallah-14/unslop](https://github.com/MohamedAbdallah-14/unslop), [asavvin-pixel/unslop](https://github.com/asavvin-pixel/unslop), [woerndl/unsloppify](https://github.com/woerndl/unsloppify), [mnapoli/skills](https://github.com/mnapoli/skills), and the `cursor/plugins` `pstack` base (surfaced via [ui-skills.com](https://www.ui-skills.com/skills/cursor/unslop)).

And to the research that shaped the structural pass: Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (CC BY-SA 4.0, used as a factual reference), the [StoryScope](https://github.com/jenna-russell/storyscope) paper (arXiv:2604.03136), the UMD / Google DeepMind cliché-removal study, [Berens & Kobak's](https://github.com/berenslab/llm-excess-vocab) excess-vocabulary analysis, and the [Google developer style guide](https://developers.google.com/style/word-list).

## License

MIT — see [LICENSE](./LICENSE).
