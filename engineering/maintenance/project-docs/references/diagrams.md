# Diagrams

Project-level docs carry graphs at several levels and in several forms. The contract fixes what must
be present; this file says which form fits which shape, where the pictures come from, and the one
boundary that keeps `docs/` from turning into a dump of generated graphs.

## Format

Mermaid, in a ` ```mermaid ` fenced block, inline in the markdown. It diffs as text, renders
in GitHub and most editors, needs no build step, and commits no binary. Two exceptions:

- A **cross-project / portfolio dashboard** (docs coverage across many projects, live) is better as an
  HTML artifact than as mermaid in a file. Off-project and interactive is the right call there.
- A **rendered SVG/PNG** only when a doc needs a visual mermaid cannot do, and even then prefer
  committing the source and generating on build over committing the image.

## Two tracks, kept apart

There are two kinds of graph, and only one belongs in `docs/`:

- **Project-level structure graphs** — curated, authored here, in `docs/`. Context, components,
  topology, build/deps, lifecycle, flow. These are what the contract requires.
- **Code-level graphs** — the public API surface, the module dependency graph, call and data-flow
  on functions. These change every commit, so hand-authoring them is a trap. They are _generated_
  from the code (rustdoc/API docs, or on-demand from a code-graph tool) and live with the code.
  `docs/` **links** to them; it never pastes them in.

The handoff: `docs/` goes down to the subsystem/component level and stops. Below that it references
the generated track. The one allowed crossover is seeding the component view (below) from a code
graph, then curating it. Raw call graphs never land in `docs/`.

## The level ladder

| Level            | Where                         | Form                          | Example                                         |
| ---------------- | ----------------------------- | ----------------------------- | ----------------------------------------------- |
| Context (L1)     | `overview.md`, mandatory      | flowchart / C4-context        | the project vs the external systems it talks to |
| Component (L2)   | `overview.md`, mandatory      | flowchart / C4-container      | the major parts inside and how they relate      |
| Topology         | `overview.md` when infra-ish  | flowchart / deployment        | hosts, VMs, network planes                      |
| Build / deps DAG | `overview.md` or `spec.md`    | `graph` / DAG                 | deploy order, a build-and-deploy pipeline       |
| Lifecycle        | `spec.md` or the relevant ADR | `stateDiagram`                | a state machine, a status pipeline              |
| Flow / sequence  | `spec.md`, per subsystem      | `sequenceDiagram` / flowchart | a request path, a recovery sequence             |

`overview.md` must carry at least the context or component view. `spec.md` carries at least one
subsystem view, and in practice one per subsystem. The **form** is the author's call: pick the
mermaid type that matches the shape of the thing — a state machine for a lifecycle, a sequence for
an ordered flow, a DAG for dependencies, a flowchart or C4 for structure. Using the wrong form (a
flowchart for what is really a state machine) is a review finding, not a validator one.

## Seeding from a code graph

For a code project, do not draw the component view from memory. Pull the real modules and edges from a
code-graph tool (clustering gives the de-facto modules; a call/trace query gives the real edges),
then curate that into the L2 diagram so it reflects reality instead of intention. For a non-code
project (infra as code, a docs project), derive the diagram from the structure directly: the dependency
DAG of deploy units, a recovery chain, an idea lifecycle.

## Currency

A diagram seeded from the code graph re-reflects reality when regenerated. A hand-drawn one
(topology, a portfolio map) goes stale silently. The validator can only confirm a diagram is
present, never that it is right, so hand-drawn diagrams lean on the staleness review knob and on
being redrawn when the thing they picture changes.
