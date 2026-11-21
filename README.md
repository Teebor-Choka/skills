# Skills — Public

Portable [Agent Skills](https://code.claude.com/docs/en/skills) for Claude Code, Codex, and OpenCode.

## Skills

Layout: `<domain>/[<group>/]<plugin>/skills/<skill>`; a domain with one plugin is the plugin root
(`research`, `knowledge`, `education`). The host shows `plugin:skill`.

| Plugin          | Skill               | What it does                                                            |
| --------------- | ------------------- | ----------------------------------------------------------------------- |
| `design`        | `architect`         | Turn a fuzzy systems requirement into an executable work package        |
|                 | `ramble`            | Grill a rough idea into a gap-closed brief for the architect            |
|                 | `decompose`         | Cut a goal into parallel units and file them                            |
|                 | `graph-engine`      | Compute parallel waves, critical path, write-set collisions             |
|                 | `project-docs`      | Standard `docs/` (overview, spec, ADRs) with a validator                |
| `swe-workflows` | `implement`         | Per-task loop: spec check, test first, isolated review, integrate       |
|                 | `find-bug`          | Turn a bug report into a committed failing test                         |
|                 | `triage`            | Turn a vague issue into implementable items with a spec                 |
|                 | `by-angle`          | Red-first block loop plus four read-only review angles                  |
|                 | `code-quality`      | Risk audit from complexity, coverage, duplication metrics               |
|                 | `document`          | Write and update one docs page per component (needs `design`)           |
|                 | (hooks, commands)   | Policy gate, skill gate, isolated-reviewer agent, work-mode commands    |
| `swe`           | `rust`              | Rust house guidelines on every change                                   |
|                 | `typescript`        | TypeScript and JavaScript house guidelines on every change              |
| `devops`        | `ci`                | Harden GitHub Actions workflows, configure Renovate                     |
|                 | `security`          | Run secret, dependency, SAST, CI scanners; AI triage                    |
|                 | `deploy`            | Deploy a revision and verify it from real logs or state                 |
| `harness`       | `assign`, `pull`    | Multi-agent runs over a shared board                                    |
|                 | `tracker`           | Live dependency map of a multi-unit build's progress                    |
|                 | `policy`            | The `.agents/policy` format and loader                                  |
|                 | `session-hygiene`   | Handoffs and session nudges, plus a statusline script                   |
|                 | (hooks)             | Guard hooks for every session, see [its README](./ai/harness/README.md) |
| `models`        | `extension-author`  | Author and port skills and plugins across agents                        |
|                 | `reflect`           | Mine sessions for agent struggles and propose fixes                     |
|                 | `tiers`             | Route each subagent to the cheapest model tier (agents, guard hook)     |
| `writing`       | `unslop`            | Remove AI tells from prose                                              |
|                 | `prose-craft`       | Compose and tighten prose                                               |
| `voice`         | `voice-style`       | Always-on plain-voice output style and its `unslop-mode` command        |
| `presentation`  | `patterns`          | Plan, build or review a talk with 88 patterns and antipatterns          |
|                 | `prep`              | Prepare a talk end to end: structure, build, rehearse                   |
| `publishing`    | `blog-syndication`  | Cross-post one blog post to Astro, dev.to, Medium and Substack          |
| `research`      | `forge-idea`        | Stress-test an idea with parallel agents                                |
|                 | `grounded-research` | Research under a fixed evidence contract                                |
| `knowledge`     | `llm-wiki`          | Build and query a linked Markdown wiki                                  |
|                 | `media-digest`      | Digest yt-dlp media and web articles into loss-checked notes            |
| `education`     | `find-ai-moat`      | Find where your work complements AI                                     |
| `nix`           | `nix`               | Nix + direnv dev workflow traps                                         |
| `git`           | `workflow`          | Git and PR workflow; git-guard hooks and the pr-watcher agent           |
| `security`      | `yubikey`           | Hardware-backed keys: offline OpenPGP root, FIDO2 SSH, signing          |

## Install

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills
```

One plugin:

```bash
claude plugin marketplace add https://github.com/Teebor-Choka/skills --plugin research
```

## Acknowledgements

### architect

The [`architect`](./engineering/design/skills/architect/SKILL.md) skill was written from scratch, drawing on established architecture literature and document standards for their ideas, methodology, and a few short attributed quotes; it reproduces no substantial text from any of them, and references the one copyleft source (arc42, CC BY-SA) by concept only. With thanks to John Ousterhout (_A Philosophy of Software Design_); Mark Richards & Neal Ford (_Fundamentals of Software Architecture_, _Building Evolutionary Architectures_, _Software Architecture: The Hard Parts_); Martin Fowler (monolith-first); Michael Nygard (ADRs) and [MADR](https://adr.github.io/madr/); Alistair Mavin ([EARS](https://alistairmavin.com/ears/)); [arc42](https://arc42.org/overview); and Simon Brown ([C4 model](https://c4model.com/)).

Its graph-engineering step ([`references/graph-patterns.md`](./engineering/design/skills/graph-engine/references/graph-patterns.md)) is grounded in the workflow / parallel / multi-agent-orchestration literature, every citation web-verified and authority-tagged, with the state of the art through 2026 folded in: the van der Aalst Workflow Patterns paper (2003), GPTSwarm (ICML 2024) and AFlow (ICLR 2025) on agents-as-optimizable-graphs, MaAS (ICML 2025) on query-dependent workflow-graph design, the topology-effects work of Shen et al. (EMNLP 2025) with G-Designer and AgentPrune/AGP, the MAST failure taxonomy (Cemri et al. 2025), and the Yue et al. 2026 survey of workflow optimization as agentic computation graphs. Full attribution with links, license notes, and preprint flags is in [engineering/architect/references/sources.md](./engineering/design/skills/architect/references/sources.md) and [graph-patterns.md](./engineering/design/skills/graph-engine/references/graph-patterns.md).

Grounding the current state can optionally run through a code graph, single- or multi-repo, via a code indexing MCP when available, with a graceful fall back to manual reading otherwise ([`references/code-graphing.md`](./engineering/design/skills/architect/references/code-graphing.md)).

### presentation

The [`presentation`](./communication/presentation/skills/patterns/SKILL.md) plugin is built on the teachings of Neal Ford, _Presentation Patterns_ (Ford, McCullough, Schutta, Addison-Wesley, 2012). The pattern names are theirs; the entries are short paraphrased guidance, and no book text is bundled.

### unslop

The [`unslop`](./communication/writing/skills/unslop/SKILL.md) skill was not written from scratch. It was built by pooling the strongest open "unslop" (de-AI-writing) agent skills on GitHub, deduplicating their rules and word lists, and folding in the research they cite, then restructuring the result around a structure-first pass (surface word-swaps alone barely move AI detection). Full attribution with links is in [model/tools/unslop/references/sources.md](./communication/writing/skills/unslop/references/sources.md).

With thanks to the authors of the MIT-licensed skills we pooled from: [theclaymethod/unslop](https://github.com/theclaymethod/unslop), [mshumer/unslop](https://github.com/mshumer/unslop), [MohamedAbdallah-14/unslop](https://github.com/MohamedAbdallah-14/unslop), [asavvin-pixel/unslop](https://github.com/asavvin-pixel/unslop), [woerndl/unsloppify](https://github.com/woerndl/unsloppify), [mnapoli/skills](https://github.com/mnapoli/skills), and the `cursor/plugins` `pstack` base (surfaced via [ui-skills.com](https://www.ui-skills.com/skills/cursor/unslop)).

And to the research that shaped the structural pass: Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (CC BY-SA 4.0, used as a factual reference), the [StoryScope](https://github.com/jenna-russell/storyscope) paper (arXiv:2604.03136), the UMD / Google DeepMind cliché-removal study, [Berens & Kobak's](https://github.com/berenslab/llm-excess-vocab) excess-vocabulary analysis, and the [Google developer style guide](https://developers.google.com/style/word-list).

## License

MIT — see [LICENSE](./LICENSE).
