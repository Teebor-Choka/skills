# Skills — Public

Portable [Agent Skills](https://code.claude.com/docs/en/skills) for Claude Code, Codex, and OpenCode.

## Skills

Layout: `<domain>/<plugin>/skills/<skill>`. The host shows `plugin:skill`.

| Plugin              | Skill               | What it does                                                     |
| ------------------- | ------------------- | ---------------------------------------------------------------- |
| `design`            | `architect`         | Turn a fuzzy systems requirement into an executable work package |
|                     | `ramble`            | Grill a rough idea into a gap-closed brief for the architect     |
|                     | `decompose`         | Cut a goal into parallel units and file them                     |
|                     | `graph-engine`      | Compute parallel waves, critical path, write-set collisions      |
|                     | `policy`            | The `.agents/policy` format and loader                           |
|                     | `project-docs`      | Standard `docs/` (overview, spec, ADRs) with a validator         |
| `review`            | `by-angle`          | Red-first block loop plus four read-only review angles           |
|                     | `code-quality`      | Risk audit from complexity, coverage, duplication metrics        |
| `swe`               | `rust`              | Rust house guidelines on every change                            |
|                     | `typescript`        | TypeScript and JavaScript house guidelines on every change       |
| `orchestrate`       | `assign`, `pull`    | Multi-agent runs: dispatcher or peer swarm over a shared board   |
| `models`            | `extension-author`  | Author and port skills and plugins across agents                 |
|                     | `reflect`           | Mine sessions for agent struggles and propose fixes              |
| `writing`           | `unslop`            | Remove AI tells from prose                                       |
|                     | `prose-craft`       | Compose and tighten prose                                        |
| `forge-idea`        | `forge-idea`        | Stress-test an idea with parallel agents                         |
| `grounded-research` | `grounded-research` | Research under a fixed evidence contract                         |
| `llm-wiki`          | `llm-wiki`          | Build and query a linked Markdown wiki                           |
| `media-digest`      | `media-digest`      | Transcribe any yt-dlp media and write a loss-checked summary     |
| `find-ai-moat`      | `find-ai-moat`      | Find where your work complements AI                              |
| `github-actions`    | `github-actions`    | Harden workflows, configure Renovate                             |
| `dep-pr-triage`     | `dep-pr-triage`     | Fix red Dependabot and Renovate PRs; never merges                |
| `nix`               | `nix`               | Nix + direnv dev workflow traps                                  |

## Install

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills
```

One plugin:

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills --plugin forge-idea
```

## Acknowledgements

### architect

The [`architect`](./engineering/design/skills/architect/SKILL.md) skill was written from scratch, drawing on established architecture literature and document standards for their ideas, methodology, and a few short attributed quotes; it reproduces no substantial text from any of them, and references the one copyleft source (arc42, CC BY-SA) by concept only. With thanks to John Ousterhout (_A Philosophy of Software Design_); Mark Richards & Neal Ford (_Fundamentals of Software Architecture_, _Building Evolutionary Architectures_, _Software Architecture: The Hard Parts_); Martin Fowler (monolith-first); Michael Nygard (ADRs) and [MADR](https://adr.github.io/madr/); Alistair Mavin ([EARS](https://alistairmavin.com/ears/)); [arc42](https://arc42.org/overview); and Simon Brown ([C4 model](https://c4model.com/)).

Its graph-engineering step ([`references/graph-patterns.md`](./engineering/design/skills/graph-engine/references/graph-patterns.md)) is grounded in the workflow / parallel / multi-agent-orchestration literature, every citation web-verified and authority-tagged, with the state of the art through 2026 folded in: the van der Aalst Workflow Patterns paper (2003), GPTSwarm (ICML 2024) and AFlow (ICLR 2025) on agents-as-optimizable-graphs, MaAS (ICML 2025) on query-dependent workflow-graph design, the topology-effects work of Shen et al. (EMNLP 2025) with G-Designer and AgentPrune/AGP, the MAST failure taxonomy (Cemri et al. 2025), and the Yue et al. 2026 survey of workflow optimization as agentic computation graphs. Full attribution with links, license notes, and preprint flags is in [engineering/architect/references/sources.md](./engineering/design/skills/architect/references/sources.md) and [graph-patterns.md](./engineering/design/skills/graph-engine/references/graph-patterns.md).

Grounding the current state can optionally run through a code graph, single- or multi-repo, via a code indexing MCP when available, with a graceful fall back to manual reading otherwise ([`references/code-graphing.md`](./engineering/design/skills/architect/references/code-graphing.md)).

### unslop

The [`unslop`](./writing/writing/skills/unslop/SKILL.md) skill was not written from scratch. It was built by pooling the strongest open "unslop" (de-AI-writing) agent skills on GitHub, deduplicating their rules and word lists, and folding in the research they cite, then restructuring the result around a structure-first pass (surface word-swaps alone barely move AI detection). Full attribution with links is in [model/tools/unslop/references/sources.md](./writing/writing/skills/unslop/references/sources.md).

With thanks to the authors of the MIT-licensed skills we pooled from: [theclaymethod/unslop](https://github.com/theclaymethod/unslop), [mshumer/unslop](https://github.com/mshumer/unslop), [MohamedAbdallah-14/unslop](https://github.com/MohamedAbdallah-14/unslop), [asavvin-pixel/unslop](https://github.com/asavvin-pixel/unslop), [woerndl/unsloppify](https://github.com/woerndl/unsloppify), [mnapoli/skills](https://github.com/mnapoli/skills), and the `cursor/plugins` `pstack` base (surfaced via [ui-skills.com](https://www.ui-skills.com/skills/cursor/unslop)).

And to the research that shaped the structural pass: Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (CC BY-SA 4.0, used as a factual reference), the [StoryScope](https://github.com/jenna-russell/storyscope) paper (arXiv:2604.03136), the UMD / Google DeepMind cliché-removal study, [Berens & Kobak's](https://github.com/berenslab/llm-excess-vocab) excess-vocabulary analysis, and the [Google developer style guide](https://developers.google.com/style/word-list).

## License

MIT — see [LICENSE](./LICENSE).
