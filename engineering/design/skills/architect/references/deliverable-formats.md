# Visual & presentation deliverables

The work package is markdown-first: the markdown IS the deliverable. Visuals are additive. The
mandatory DAG diagram lives in `development-graph.md` (produced when the spec's blocks are planned
into an execution graph); this file covers only the optional presentation layer: diagrams and a
shareable rendering for readers outside the terminal.

## Diagrams (mermaid, in-repo)

Draw the load-bearing diagrams as mermaid fenced blocks inside the markdown, so they render in the
repo and need no external tool or build step. Give visuals a defined ladder (C4-style), one
abstraction per diagram, rather than one crowded picture:

- **L1 Context** in the README: the system as one box among its neighbours and users.
- **L2 Container / component**: the buildable nodes and how they connect. This is the block graph.
- **Deployment**: what the orchestrator brings up and what observability watches (Phase B).
- **Execution DAG**: the build order, waves, and loops (mandatory, in `development-graph.md`).

Keep each diagram to one zoom level. A diagram that needs a legend to tell five kinds of arrow
apart is doing the job of three diagrams. C4 model reference: https://c4model.com/

## Shareable rendering (optional)

For stakeholders who will not read markdown in a terminal, a single self-contained HTML rendering
of the proposal is a fine convenience: self-contained (no external requests), theme-aware
(light/dark), responsive. It is a rendering of the proposal, never a separate document. When the
proposal changes, the markdown is authoritative and the HTML is regenerated, never edited on its
own.

When the share is a **stakeholder review of the whole package**, not just the proposal, inline every
artifact into that one `index.html` rather than linking the sibling docs. A reader opening the HTML
outside the repo can't follow a relative link to `decision-log.md` or a `block-*.md` brief, so a
linked review is a review full of dead ends. One self-contained file with all artifacts inlined
reads end to end anywhere; it is still a rendering, regenerated from the authoritative markdown.

Use whatever rendering and publishing capability your agent host provides. The concrete per-agent
wiring lives in `adapters/` (on Claude Code, the `Artifact` tool and the `artifact-diagramming` /
`artifact-design` skills; other hosts use their own). Published visuals and HTML are a convenience
layer, never the source of truth, and sharing them outside the team is the human's call, not the
agent's.
