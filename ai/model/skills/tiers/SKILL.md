---
name: tiers
description: Choose the model tier for a subagent or task (light, execution, reasoning) and resolve it to a model through the tier map. Use when spawning a subagent, dispatching a task to a cheaper model, or editing the tier-to-model map.
license: MIT
compatibility: any
---

# Model tiers

Pick the lowest tier that does the task correctly. Move up only when the work needs more reasoning,
and re-dispatch that one task, not the whole run.

| Tier        | Use for                                                                                                         | Agent      |
| ----------- | --------------------------------------------------------------------------------------------------------------- | ---------- |
| `light`     | Retrieval, extraction, classification, log and diff scans, status and poll loops. Reads and reports, no decide. | `reader`   |
| `execution` | The default for building: implement a specified change, write code, tests, docs, routine debugging.             | `builder`  |
| `reasoning` | Architecture, design, specs, novel debugging, adversarial review, synthesis. Rare and deliberate.               | `reasoner` |

A watch or poll loop is `light`, never `reasoning`.

## The map

`tiers.json` in the plugin root is the only place a tier meets a model name, per harness:

```json
{ "tiers": { "light": { "claude": "haiku", "codex": "TODO" } } }
```

`TODO` marks a model id not chosen yet. A tier with no key for the harness counts as absent, the same as
`TODO`. Tier keys are `light`, `execution`, `reasoning` and `speed`; other keys are ignored. The
`model-tier-guard` hook reads the map for the harness in `AGENT_HARNESS` (default `claude`) and accepts
either a tier name or a model from the map as the subagent's `model`. An explicit model name is never
remapped, and a model the Agent tool takes but the map does not list (`fable`, a full `claude-...` id) passes through unchanged on `claude`. A rewrite (a tier name, or a default for an agent) carries no permission decision, so your own permission rules still apply. A spawn of `reader`, `builder` or `reasoner` (with or without the `models:` prefix) with no
model gets its tier's model. For `claude`, a tier the map leaves absent falls back to haiku, sonnet or
opus. When the map is unreadable or holds no model for the harness, the hook fails open and says so in one
line. Point `AGENT_TIERS_FILE` at another file to test a map.

Each agent file declares its tier in a `tier:` frontmatter key. Its `tools:` list uses Claude Code tool
names (`Read`, `Grep`, `Glob`, `Bash`, `Edit`, `Write`). The per-harness agent adapter, which would map
the tier and the tools to another harness's names, is not built yet.
