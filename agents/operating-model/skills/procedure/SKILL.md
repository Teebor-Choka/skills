---
name: procedure
description: >
  Define, extend or validate a procedure: a named graph of stages (what runs, in what order,
  what each stage consumes and produces) for any kind of work, such as software delivery, a
  campaign or a research track. Use when asked to define or change how work flows end to end,
  add, remove or reorder a stage, insert a review or release step, give each agent a clear scope,
  or check that a procedure file is wired correctly. A stage owner reads its row to learn its
  input, output and limits. Not for settings values such as strictness or interaction style
  (use policy), not for the Claude Code Workflow tool, and not for GitHub Actions workflow YAML.
license: MIT
compatibility: any
metadata:
  version: "1.0.0"
---

# procedure: a named graph of stages

A procedure says which stages exist, how they connect, and what passes between them. It does not
set how strict a stage is: that is `policy`. The two work alone. `policy` needs no procedure. A
procedure needs no policy beyond the optional `procedure: <name>` key that selects it.

## Format

A Markdown file. Frontmatter uses the `policy` subset (scalars, inline lists `[a, b]`, nested maps by
indentation; no inline `{}` maps, no block lists). The body is free prose. Example:
[`assets/example-campaign-ops.md`](assets/example-campaign-ops.md).

Stage keys, all under `stages.<id>`:

| key                    | meaning                                                                      |
| ---------------------- | ---------------------------------------------------------------------------- |
| `needs`                | List of stage ids that run first. No `needs` marks an entry stage.           |
| `consumes`, `produces` | Lists of artifact kinds. Kinds are open strings.                             |
| `skill`                | Who executes the stage. Free string.                                         |
| `when`                 | Condition to run. Free string; the stage owner interprets it.                |
| `on-fail`              | Map: `to` (a stage id) and optional `bound`. A retry loop, not a dependency. |
| `review`               | List of review angles for this stage.                                        |
| `tier`                 | Model tier: `reasoning`, `execution`, `light`, `speed`.                      |
| `floor`                | `true` marks a stage no delta may disable.                                   |
| `disabled`             | In a delta: `true` removes the stage.                                        |

Top-level `trigger` is a free map for what starts the procedure. Any other key is allowed and
ignored by the validator.

## Rules the validator enforces

1. Every `needs` entry names a stage. `on-fail.to` names a stage.
2. `needs` has no cycle. `on-fail` is not a dependency, so a retry loop is valid.
3. `needs`, `consumes`, `produces` and `review` are lists.
4. A stage with `needs` consumes only kinds an upstream stage produces. An entry stage consumes
   external input and is not checked.
5. A kind whose upstream producers all carry `when` is rejected: skip the condition and the
   consumer has no input.
6. A delta cannot disable a `floor` stage.

The validator checks structure, never content. Run
`python3 scripts/validate_procedure.py FILE`, or `--base BASE --delta DELTA` to check an overlay.
Both exit 1 on any error.

## Layering

A delta overlays a baseline per stage id: its keys replace the baseline's, `disabled: true` removes
the stage, a new id adds one. Suggested locations, mirroring `policy`: baseline shipped with the
procedure's owner, then `~/.config/agents/procedures/<name>.md`, then
`<repo>/.agents/procedures/<name>.md`, local last. This skill ships the merge and the validator,
not a resolver that finds those files.

## What a stage owner does

1. Read the stage row. Take only the `consumes` kinds as input.
2. Do the work in the stage's scope and nothing downstream.
3. Emit every `produces` kind. A missing kind blocks the next stage.
4. On failure, follow `on-fail`. With none, escalate to the owner. Do not guess.
5. Hand off by writing the artifact where the next stage reads it.

The `floor` flag is checked here, at validation. Runtime blocking is the hook layer's job, and the
shipped git hooks block only in team mode: they warn in single mode. Do not claim the floor holds
unconditionally.
