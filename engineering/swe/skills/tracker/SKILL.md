---
name: tracker
description: >
  Show the progress of a multi-unit build as a live dependency map: one circle per unit, one
  column per wave, a spinning ring for work in progress, a lock for a pending owner decision, and
  a target at the right edge. Use when a build, migration or plan has several dependent units and
  the owner wants to see status at a glance, and after each unit changes state. Not for a single
  task, a burndown chart, or a ticket board.
---

# Tracker

One page shows every unit of a build, what it needs, and what it must deliver. The page is a
fixed template. Only its data block changes.

## Template

[assets/tracker.html](assets/tracker.html) is the template. Do not edit its markup, CSS or
script. Copy it, then replace the data block: the lines from `var ASOF=` up to, but not including,
`var LABEL=`. The block holds `ASOF`, `LEAD`, `FOOT`, `U` and `TARGET`.

The template ships with a worked example (the 21-unit organization-model build). Replace all of it.

## Data block

| Name     | Meaning                                                                                                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------ |
| `ASOF`   | Date of the status, `YYYY-MM-DD`.                                                                                        |
| `LEAD`   | Intro sentence under the title: what is built, how many units and waves.                                                 |
| `FOOT`   | Closing note under the list, for example how statuses are checked.                                                       |
| `U`      | Array of units, in build order.                                                                                          |
| `TARGET` | The one end goal. It has the same fields as a unit, `st:"target"` and `dep`: the ids of the units that finish the build. |

The page derives the wave count and the target column from `U`. Nothing else needs editing.

Unit fields:

| Field  | Value                                                                         |
| ------ | ----------------------------------------------------------------------------- |
| `id`   | Short unique id, such as `U13a`. Keep it under 5 characters.                  |
| `w`    | Wave number, 1 or more. A unit sits in a later wave than every unit it needs. |
| `name` | Two to four words.                                                            |
| `st`   | `done`, `active`, `wait` or `gate`.                                           |
| `note` | Short state label, for example `in review`, `signed`, `waits for O4`.         |
| `dep`  | Array of ids this unit needs.                                                 |
| `what` | One sentence: what the unit is.                                               |
| `tgt`  | One sentence: what it must deliver. A checkable result, not an activity.      |

Status values:

| `st`     | Draw          | Use when                                                                  |
| -------- | ------------- | ------------------------------------------------------------------------- |
| `done`   | Tick          | The unit is accepted, not just written.                                   |
| `active` | Spinning ring | An agent writes it, or a review or fix is in progress.                    |
| `gate`   | Amber, lock   | The unit waits for a decision only the owner can make. Name it in `note`. |
| `wait`   | Dashed grey   | The unit is queued behind its dependencies.                               |

## Procedure

1. Read the build state from its source of truth: the run log, the graph spec or the issues.
   Do not write a status from memory.
2. Map each unit to one `st` value. A unit is `done` only after its acceptance check passed.
3. Copy the template to a scratch directory. Replace the data block.
4. Check that the script parses. With no Node, run `uv run --with esprima python` and call
   `esprima.parseScript` on the script text.
5. Publish the page as a hosted artifact. On the first publish, set the icon to `graph` and add a
   one-sentence description. Keep the title `Build Map`, or name it after the build, and keep it
   the same on later publishes.
6. To update, publish the same file again. Change the data block only. Show the page to the
   owner after each publish.
7. Update the page after every unit changes state and after every owner decision.

## Rules

- The page shows state. It decides nothing. A unit moves to `done` through the build's own
  review and acceptance gates.
- Keep `what` and `tgt` to one sentence each. The detail panel and the component list show them.
- Show a pending owner decision as `gate`, never as `wait`. The owner must see what blocks the build.
- Do not add colors, fonts or animation. The template honors `prefers-reduced-motion` and both themes.
- Do not put secrets, local paths or private ticket text in the data. The page can be shared.
