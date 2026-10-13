# The docs contract

The single source of truth for project-level documentation. The authoring flow writes to it; the
validator (`scripts/validate_docs.py`) enforces it. Both read this file, so they cannot drift.
Everything here is mechanically checkable. Craft guidance that needs judgment lives in `flow.md` and
`diagrams.md`, not here.

A **project** is any coherent unit of work an agent runs against: a code repo, a subproject, or a
non-code effort (infra, research, strategy). The contract is the same for all of them; what varies
is whether the deep spec is warranted (see "Spec opt-in").

## Required tree

Every documented project has, at its root:

```
docs/
  overview.md              # required
  spec.md                  # optional, opt-in by size (see below)
  decisions/
    README.md              # required: the index
    <slug>.md              # one ADR per decision, >=1
AGENTS.md                  # required: points into docs/
```

- `overview.md` and `decisions/` (index + at least one ADR) are **always** required.
- `spec.md` is **opt-in by size**: required only when the project has real behavior to specify (a
  pipeline, a protocol, stateful subsystems). A trivial project (a static page, a docs-only or
  notes-only effort) omits it. See "Spec opt-in" below. When present, it must conform.
- A project may keep extra docs (`design/`, `providers/`, `architecture/`); the contract neither
  requires nor forbids them, and the validator ignores them.

## Frontmatter

Every doc under `docs/` starts with YAML frontmatter. Keys per kind:

| File                  | `kind`            | required keys                           | optional keys                 |
| --------------------- | ----------------- | --------------------------------------- | ----------------------------- |
| `overview.md`         | `overview`        | `title`, `kind`, `project`, `updated`   | —                             |
| `spec.md`             | `spec`            | `title`, `kind`, `project`, `updated`   | —                             |
| `decisions/README.md` | `decisions-index` | `title`, `kind`, `project`, `updated`   | —                             |
| `decisions/<slug>.md` | (ADR, no `kind`)  | `title`, `status`, `project`, `updated` | `supersedes`, `superseded-by` |

- `title`: non-empty string.
- `project`: the project's short name; the same value across every doc in that project. `repo` is
  accepted as a deprecated alias (the validator reads it but prefers `project`).
- `updated`: an ISO date `YYYY-MM-DD`.
- `status` (ADR only): one of `proposed`, `accepted`, `superseded`, `rejected`.

## ADR structure

Each `decisions/<slug>.md`:

- Filename `<slug>` is kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`), naming the decision, not numbered.
  Renaming is cheaper than renumbering, and the index carries the order.
- Body contains all four section labels, in order: **Context**, **Decision**, **Consequences**, and
  a set-aside-alternatives label (one of **Set aside**, **Alternatives**, **Rejected**). House style
  writes them as bold leads (`**Context.** ...`); `## Context` headings also pass.
- The set-aside section records the alternative that was considered and dropped, so it is not
  re-proposed without new information. An ADR with no alternative is usually a decision that was
  never really a choice; say so explicitly rather than omitting the section.

## Decisions index

`decisions/README.md` lists every ADR in the directory. The validator checks both directions: every
`<slug>.md` (except `README.md`) appears as a link in the index, and every link in the index
resolves to a file that exists. An index that silently drifts from the directory is the failure this
check exists to catch.

## AGENTS.md pointer

Root `AGENTS.md` exists and references `docs/overview.md` and `docs/decisions/`. It is the agent
entry point; it points into `docs/`, it does not restate it. The validator checks that both paths
are mentioned.

## Diagram-level matrix

Diagrams are mermaid fenced blocks, in-file, so they version and diff with the prose. What must be
present:

| Doc           | Mandatory                                                  |
| ------------- | ---------------------------------------------------------- |
| `overview.md` | at least one mermaid block (the context or component view) |
| `spec.md`     | at least one mermaid block (a subsystem view)              |
| ADRs          | none (add one only where the decision is structural)       |

The validator checks presence, never correctness. "A diagram per subsystem" in `spec.md` and the
choice of form (flowchart, sequence, state, DAG) are standards in `diagrams.md`, enforced by review,
not the script. Code-level graphs (API surface, call/data-flow) are a separate generated track and
are **not** authored into `docs/`; link to them instead.

## Spec opt-in

A project needs `spec.md` when getting it wrong would cost something: it has a runtime pipeline, a
protocol or wire format, stateful subsystems, or non-obvious failure/recovery behavior. It does not
need one when the project is a static artifact, a thin wrapper, or pure documents. The author
decides at authoring time and records the call in `overview.md` (a one-line "no deep spec: REASON"
when omitted). The validator does not force `spec.md`; it only conforms one that exists.

## What the validator does not do

It checks structure, not content quality or currency. It cannot tell whether a diagram is accurate,
whether prose is terse, or whether an ADR is still true. Those are the authoring flow's job (write it
right) and the optional staleness review knob's job (catch it going stale).
