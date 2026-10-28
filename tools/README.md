# Tools skills

General-purpose skills for working with ideas, knowledge, and specific systems. Each is a
portable Agent Skill (`SKILL.md`) that runs unchanged on Claude Code, Codex, and OpenCode —
see [agent-extension-author](../model/tools/agent-extension-author/SKILL.md) for the cross-agent model.

| Skill                                             | What it does                                                                                                                                   | Reach for it when                                                                          |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [forge-idea](./forge-idea/SKILL.md)               | Forge a rough idea or thesis into a viable one — fan out parallel agents to stress-test each branch, prune the dead ones, reshape the rest     | "will this actually work?", "tear this apart", pressure-testing a strategy or architecture |
| [llm-wiki](./llm-wiki/SKILL.md)                   | Build, grow, and query a linked Markdown knowledge wiki an LLM can navigate, every claim cited                                                 | "digest my notes", "what do my notes say about X", keeping a second brain healthy          |
| [decompose](./decompose/SKILL.md)                 | Cut a goal into parallel units (write-set, acceptance, tier), check the cut with graph-engine, file the items                                  | "split this work", "divide this for the agents", turning a design into work items          |
| [graph-engine](./graph-engine/SKILL.md)           | Work-division engine: from units with dependencies and write-sets, compute collision-free parallel waves, the critical path, and barriers.     |
| [grounded-research](./grounded-research/SKILL.md) | Research a question under a fixed evidence contract: primary sources first, every claim cited with URL and date, fact kept apart from hearsay. |
| [policy](./policy/SKILL.md)                       | The shared .agents/policy format and loader: layered (global plus per-repo), open, with a basic default.                                       |
| [ramble](./ramble/SKILL.md)                       | Turn a rough idea into an aligned, gap-closed brief for the architect through a relentless grilling interview.                                 |

`forge-idea` and `llm-wiki` carry optional multi-agent workflow support (parallel branch
fan-out and parallel ingestion/query) in their `references/cross-agent.md`.
