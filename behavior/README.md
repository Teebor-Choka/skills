# Behavior plugins

Plugins that shape how agents work together. Each is a plugin with namespaced skills, like
`swe-process:implement`.

| Plugin                        | Skills                                                                | What it does                                                                                                                                                                                                                                                         |
| ----------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [orchestrate](./orchestrate/) | `orchestrate:pull` (alias swarm), `orchestrate:assign` (alias direct) | Coordinate several agents on one goal through a shared work board. Shared mechanics (claim, heartbeat lease, reap, hand-off by writing, escalation ladder) live in `orchestrate/references/mechanics.md`; an owner-approved charter defines roles, states and gates. |

Aliases are trigger words in each skill's description. Plugin skills have no alias field.
`decompose` (in `tools/`) cuts the work into units before either mode runs.
