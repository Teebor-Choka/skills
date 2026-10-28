# Skills — Public

Public AI agent skills for [Claude Code](https://claude.ai/code) and compatible agent hosts.

## Skills

Grouped by source directory (see [Repository layout](#repository-layout)). Every skill is a
portable Agent Skill (`SKILL.md`) that runs unchanged on **Claude Code**, **Codex**, and
**OpenCode**; the [agent-extension-author](./model/tools/agent-extension-author/SKILL.md) skill documents that
cross-agent model. Each category has its own README with fuller blurbs.

### tools — [details](./tools/README.md)

| Skill                                                   | Description                                                                                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| [forge-idea](./tools/forge-idea/SKILL.md)               | Forge a rough idea into a viable one by fanning out parallel agents to stress-test and prune branches                                          |
| [llm-wiki](./tools/llm-wiki/SKILL.md)                   | Build, grow, and query a linked Markdown knowledge wiki an LLM can navigate                                                                    |
| [decompose](./tools/decompose/SKILL.md)                 | Cut a goal into parallel units, check the cut with graph-engine, file the items                                                                |
| [graph-engine](./tools/graph-engine/SKILL.md)           | Work-division engine: from units with dependencies and write-sets, compute collision-free parallel waves, the critical path, and barriers.     |
| [grounded-research](./tools/grounded-research/SKILL.md) | Research a question under a fixed evidence contract: primary sources first, every claim cited with URL and date, fact kept apart from hearsay. |
| [policy](./tools/policy/SKILL.md)                       | The shared .agents/policy format and loader: layered (global plus per-repo), open, with a basic default.                                       |
| [ramble](./tools/ramble/SKILL.md)                       | Turn a rough idea into an aligned, gap-closed brief for the architect through a relentless grilling interview.                                 |

### behavior — [details](./behavior/README.md)

| Skill                                                                              | Description                                                                       |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [orchestrate:pull](./behavior/orchestrate/skills/pull/SKILL.md) (alias swarm)      | Peer-to-peer swarm: agents pull items from a shared board, no dispatcher relay    |
| [orchestrate:assign](./behavior/orchestrate/skills/assign/SKILL.md) (alias direct) | Thin dispatcher hands known, disjoint units to workers; leases instead of polling |

### model/tools — [details](./model/tools/README.md)

| Skill                                                                   | Description                                                                                                                    |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [prose-craft](./model/tools/prose-craft/SKILL.md)                       | Compose or revise clear, well-architected prose (Strunk & White + Pinker)                                                      |
| [unslop](./model/tools/unslop/SKILL.md)                                 | Edit prose to remove AI tells and restore a plain, human voice                                                                 |
| [agent-extension-author](./model/tools/agent-extension-author/SKILL.md) | Author, port, and harden skills and plugins across Claude Code, Codex, OpenCode, and oh-my-pi                                  |
| [session-retrospective](./model/tools/session-retrospective/SKILL.md)   | Mine agent sessions for the moments the agent struggled, then propose fixes to the skills, environment, and workflows it used. |

### engineering — [details](./engineering/README.md)

| Skill                                         | Description                                                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [architect](./engineering/architect/SKILL.md) | Turn a fuzzy systems/infra requirement into a self-contained, agent-executable work package, then execute it |

### engineering/swe — [details](./engineering/swe/README.md)

| Skill                                                                 | Description                                                                                                                         |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [rust-engineer](./engineering/swe/rust-engineer/SKILL.md)             | Enforce Rust house guidelines while writing or reviewing Rust                                                                       |
| [code-quality](./engineering/swe/code-quality/SKILL.md)               | Audit code risk from complexity/coverage/duplication metrics + comment quality (reports only)                                       |
| [review-gauntlet](./engineering/swe/review-gauntlet/SKILL.md)         | Run a block of build work through red-first roles and a read-only four-angle review gauntlet that reports findings without editing. |
| [typescript-engineer](./engineering/swe/typescript-engineer/SKILL.md) | Enforce TypeScript and JavaScript code quality and house guidelines on every TS/JS change.                                          |

### engineering/ci — [details](./engineering/ci/README.md)

| Skill                                                      | Description                                                                                                                                                        |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [github-actions](./engineering/ci/github-actions/SKILL.md) | Harden GitHub Actions workflows and configure Renovate                                                                                                             |
| [dep-pr-triage](./engineering/ci/dep-pr-triage/SKILL.md)   | Triage open Dependabot and Renovate PRs across orgs: classify each red check, apply the mechanical fix on the PR branch, push, re-check. Never merges or approves. |

### maintenance — [details](./maintenance/README.md)

| Skill                                               | Description                                                                                         |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| [project-docs](./maintenance/project-docs/SKILL.md) | Give any project a standard, enforceable `docs/` (overview, spec, ADRs) with diagrams + a validator |

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
  decompose/            # skill: decompose
behavior/
  orchestrate/          # plugin: orchestrate — skills pull + assign, shared references/
model/tools/
  unslop/               # skill: unslop
  agent-extension-author/        # skill: agent-extension-author — references/platforms + validate_skill.py
engineering/
  architect/            # skill: architect — scaffold.py + lint.py, references, adapters
engineering/swe/
  rust-engineer/        # skill: rust-engineer
  code-quality/         # skill: code-quality — workflows: measure, comments
engineering/ci/
  github-actions/       # skill: github-actions — Actions hardening + Renovate
maintenance/
  project-docs/         # skill: project-docs — docs contract, validator, diagrams
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

Grounding the current state can optionally run through a code graph, single- or multi-repo, via a code indexing MCP when available, with a graceful fall back to manual reading otherwise ([`references/code-graphing.md`](./engineering/architect/references/code-graphing.md)).

### unslop

The [`unslop`](./model/tools/unslop/SKILL.md) skill was not written from scratch. It was built by pooling the strongest open "unslop" (de-AI-writing) agent skills on GitHub, deduplicating their rules and word lists, and folding in the research they cite, then restructuring the result around a structure-first pass (surface word-swaps alone barely move AI detection). Full attribution with links is in [model/tools/unslop/references/sources.md](./model/tools/unslop/references/sources.md).

With thanks to the authors of the MIT-licensed skills we pooled from: [theclaymethod/unslop](https://github.com/theclaymethod/unslop), [mshumer/unslop](https://github.com/mshumer/unslop), [MohamedAbdallah-14/unslop](https://github.com/MohamedAbdallah-14/unslop), [asavvin-pixel/unslop](https://github.com/asavvin-pixel/unslop), [woerndl/unsloppify](https://github.com/woerndl/unsloppify), [mnapoli/skills](https://github.com/mnapoli/skills), and the `cursor/plugins` `pstack` base (surfaced via [ui-skills.com](https://www.ui-skills.com/skills/cursor/unslop)).

And to the research that shaped the structural pass: Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (CC BY-SA 4.0, used as a factual reference), the [StoryScope](https://github.com/jenna-russell/storyscope) paper (arXiv:2604.03136), the UMD / Google DeepMind cliché-removal study, [Berens & Kobak's](https://github.com/berenslab/llm-excess-vocab) excess-vocabulary analysis, and the [Google developer style guide](https://developers.google.com/style/word-list).

## License

MIT — see [LICENSE](./LICENSE).
