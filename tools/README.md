# Tools skills

General-purpose skills for working with ideas, knowledge, and specific systems. Each is a
portable Agent Skill (`SKILL.md`) that runs unchanged on Claude Code, Codex, and OpenCode —
see [skill-creator](../model/tools/skill-creator/SKILL.md) for the cross-agent model.

| Skill                               | What it does                                                                                                                               | Reach for it when                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| [forge-idea](./forge-idea/SKILL.md) | Forge a rough idea or thesis into a viable one — fan out parallel agents to stress-test each branch, prune the dead ones, reshape the rest | "will this actually work?", "tear this apart", pressure-testing a strategy or architecture |
| [llm-wiki](./llm-wiki/SKILL.md)     | Build, grow, and query a linked Markdown knowledge wiki an LLM can navigate, every claim cited                                             | "digest my notes", "what do my notes say about X", keeping a second brain healthy          |
| [hopr-debug](./hopr-debug/SKILL.md) | Load ground-truth HOPR protocol knowledge (RFC-0001–0014) so mixnet/node debugging is correct, not plausible-but-wrong                     | a node isn't relaying, tickets aren't winning, a channel won't open, no route found        |

`forge-idea` and `llm-wiki` carry optional multi-agent workflow support (parallel branch
fan-out and parallel ingestion/query) in their `references/cross-agent.md`. `hopr-debug` is a
ground-truth reference loader and stays lean.
