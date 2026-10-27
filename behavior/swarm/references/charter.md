# Charter: the process the swarm runs

The swarm skill gives mechanics. The charter gives process. **No agent starts without an
owner-approved charter.** Write it in one file in the work area and name its path in every agent's
spawn brief.

## How it gets written

1. **Owner present (default).** Interview the owner one question at a time until every field below
   has an answer. Write the answers. The owner approves the file.
2. **Owner absent (unattended run).** An agent drafts the charter. It marks every guess as
   `assumption: <text>` and files one escalation item per assumption. The swarm may start, but no
   irreversible action (merge to a protected branch, tag, publish, delete, send outside the team)
   proceeds on an unratified assumption. The owner ratifies later; the answer is recorded in the
   tradeoffs file.

An agent that meets a case the charter does not cover escalates. It does not guess.

## Required fields

| Field                | Content                                                                                                                                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Goal                 | One paragraph: what done means for the whole swarm.                                                                                                                                          |
| Specification        | Five categories: valid inputs, expected outputs, failure definition, performance or scale, dependency behaviour. A blank category is a decision nobody approved. Out of scope, with reasons. |
| Binding              | Board backend and how to reach it (default: beads, see `beads.md`).                                                                                                                          |
| Roles                | Per role: name, count, model tier, skills to load, pull set (states it may take), write scope. An empty skills list means the agent chooses fitting skills and notes them on the item.       |
| States               | The state names, allowed transitions, and which role performs each.                                                                                                                          |
| Gates                | Which transitions need a verdict, who gives it, and what it checks. Every verdict pins a revision.                                                                                           |
| Acceptance tests     | How an item's acceptance tests are written and who derives them. Do not let the author of the work write its only tests.                                                                     |
| Areas                | The `area` labels (files, modules, topics) used for affinity. Optional.                                                                                                                      |
| Stale timeout        | Minutes without heartbeat before reaping. Default 15.                                                                                                                                        |
| Irreversible actions | The list that needs a ratified decision.                                                                                                                                                     |
| Escalation ladder    | Rungs between an asking agent and the owner: which advisor roles answer which areas. Zero rungs is valid (owner only). See `escalation.md`.                                                  |
| Escalation channel   | **Mandatory.** Where owner escalations are delivered and how the owner answers. See `escalation.md`.                                                                                         |
| Curator cadence      | Minutes between board cleanups. Default 30. Optional role.                                                                                                                                   |
| Tradeoffs file       | Path to the accepted-tradeoffs file (`tradeoffs-template.md`).                                                                                                                               |
| End condition        | The check that ends the swarm, and who sets the stop flag.                                                                                                                                   |
| Reporter             | Optional. Whether a reporter runs, its cadence, its channel.                                                                                                                                 |
| Spawn-brief line     | The line every spawner puts in a brief (below).                                                                                                                                              |

## Spawn-brief line

Put this in every agent's brief, with values filled in:

```
Load skill `swarm`, role `<role>`. Charter: <path>. Board: <binding and reference>.
Agent id: <unique id>. Read and write the board directly. Do not relay through the dispatcher.
```

The dispatcher, if one exists, only spawns agents and answers escalations. It holds no state.
