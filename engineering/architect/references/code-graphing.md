# Assembling the current state with a code graph

Step 0 assembles what is actually true today, breadth first. On anything larger than a small repo, a
code graph answers "what is here, what depends on what, what breaks if this changes" far faster and
more completely than reading and grepping by hand, and it is the first coherent way to describe how
_several_ repositories fit together. This file is how to assemble through one, with a graceful fall
back to manual reading when no code-graphing tool is present.

Survey before you zoom. The order below is deliberate: pull the whole-system map _first_, then walk
down into each boundary, rather than exploring the one area you expect to change and stopping there.
The nuance that breaks a design is usually in a subsystem you never surveyed.

The flow is: **determine scope → ensure a fresh index → survey the whole system → walk each boundary →
trace flows and seams → surface hotspots → write research-notes**. Every claim still traces to a node
or a file path; anything the graph cannot resolve is flagged, not asserted.

## 1. Determine scope (which repos are the project)

- If the working directory is itself a repository, that is the default single-repo scope.
- If it is **not** a repository, or the scope is ambiguous, scan the current directory's immediate
  contents for candidate repositories (subdirectories that are git repos or code roots) and **ask the
  user two things**: (a) which of those repositories to include, and (b) what constitutes a _unit of
  project_ here, how the chosen repos group into one architecture (one service plus its libraries;
  several services that ship together; a frontend, backend, and infra set). Do not guess the grouping;
  it decides what "the system" means for the rest of the package.

## 2. Detect the capability

Use whichever graph capability is present; both of the first two qualify, and having both is better
than either, because they answer different questions (see §4). Prefer whichever has a fresh index of
the in-scope repos.

1. **codebase-memory-mcp**: a knowledge-graph MCP whose tools include `get_architecture` (whole-system
   overview _plus_ Leiden community clusters — the de-facto modules), `search_graph`, `trace_path`
   (call paths, data flow, cross-service), `query_graph` (Cypher, including per-symbol complexity and
   hotspot metrics), `get_code_snippet`, `search_code`, and `detect_changes` (change impact). This is
   the stronger instrument for the whole-system survey and for data-flow and hotspot assembly.
2. **codegraph** (https://github.com/colbymchenry/codegraph, MIT): available when its MCP tools
   (`codegraph_explore`, `codegraph_node`) are exposed to the host, or the `codegraph` CLI is on PATH.
   Strong for verbatim source + call paths + blast radius of a named area.
3. **graphify**: a future alternative; detect a `graphify-out/` index.
4. **none**: fall back to manual grounding (read the real repos and configs) and say so in
   `research-notes.md`, so a reader knows the floor was hand-built, not graph-derived.

For codegraph, the MCP tools and the CLI subcommands return the same output, so a host without the
codegraph MCP uses the identical CLI; the mapping in §4 names both.

## 3. Ensure a fresh index (build the current state first)

Ground the _current_ code, not a stale snapshot. Refresh whichever graph you use before surveying:
codebase-memory-mcp via its index/status tools (`index_status` then `index_repository` when stale or
absent); codegraph via the steps below. For each in-scope repo (codegraph):

- Check `codegraph status --json`. It reports top-level `initialized`, `nodeCount`/`edgeCount`,
  `languages`, and `pendingChanges` (its `added` / `modified` / `removed` counts), plus a nested
  `index` object whose `index.reindexRecommended` flags a stale index.
- If `initialized` is false, build the index: `codegraph init <repo>`.
- If any of `pendingChanges.{added,modified,removed}` is non-zero, or `index.reindexRecommended` is
  true, refresh it: `codegraph sync <repo>` (codegraph's own file-watcher may already have synced;
  `status` confirms).

The index lives in a `.codegraph/` directory in the repo; it is disposable and must never be committed
(the repo `.gitignore` excludes it).

## 4. Assemble through the graph, mapped to research-notes.md

Work top to bottom: the first row is the whole-system survey you do _before_ the rest, the middle rows
walk down into it, and the last row is the per-change blast radius you return to once a design is
forming.

| Question (research-notes section)                            | codebase-memory-mcp                                                                                   | codegraph                                                                                        |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Whole-system map + de-facto module clusters (the survey)     | `get_architecture`: packages, services, dependencies, and Leiden clusters with cohesion and top nodes | no system-level view; approximate by listing files and reading coupling (see below)              |
| Each subsystem with the node/file that proves it             | `search_graph` / `get_code_snippet` per cluster; `search_code` for a pattern                          | `codegraph_explore "<area>"` (or `codegraph explore`): verbatim source, call paths, blast radius |
| Load-bearing data flows and cross-service / cross-repo seams | `trace_path` mode `data_flow` and `cross_service`                                                     | `codegraph_node <symbol>` (or `codegraph node`): caller/callee trail across files                |
| Coupling and complexity hotspots (what to watch)             | `query_graph` over complexity metrics (cyclomatic, `transitive_loop_depth`, `linear_scan_in_loop`, …) | the caller/dependent counts codegraph reports per symbol and file                                |
| Where the code lives, the file structure                     | `search_graph` with a file filter; `get_architecture` packages                                        | `codegraph files --json`                                                                         |
| Blast radius of a specific change                            | `detect_changes`, or `trace_path` inbound from the change site                                        | `codegraph impact <symbol>` and `codegraph callers <symbol>`                                     |

Read coupling counts as afferent (callers in) and efferent (callees out); the high-fan-in,
high-fan-out symbols and files are the hotspots. **You still make the architectural call** — naming
module and service boundaries using the Ford and Richards coupling and quantum framing in
`principles.md`. The difference: codebase-memory-mcp's `get_architecture` gives you the de-facto
clusters (Leiden community detection) to start from and refine; codegraph has no clustering step, so
there you derive the boundaries from the coupling numbers and dependency edges yourself. Either tool
reports numbers; the boundary is your judgment.

## 5. Multi-repo (cross-repo architecture)

For a project that spans several repos: index and ground each repo, then describe the **cross-repo
picture**, which imports or calls cross a repo boundary, which repo owns which capability, and where
the seams are. codebase-memory-mcp has a dedicated cross-repo pass (`index_repository` mode
`cross-repo-intelligence`, which links routes and channels across already-indexed projects); codegraph
resolves cross-file references and some cross-language bridges. Where either cannot resolve an edge,
say so rather than asserting it. The cross-repo dependencies and the shared
choke points are what a single-repo read never surfaces, and they set the "where this plugs in today"
section of the proposal.

## 5a. Reconciling a spec or RFC against the live code

When the grounding task is to check an existing spec or RFC against what the code actually does,
deliver the cross-cutting result as a single comparison table, not prose. Pick the axes the spec
turns on (e.g. operation x property x config x count) so each row is one checkable claim and the gaps
show up as empty or mismatched cells. Iterate the table until it is complete — every operation the
spec names has a row, and every row says whether the code matches, diverges, or is missing. A prose
write-up hides exactly the omission a table forces into view.

## 6. The rule that does not change

Whether graph-derived or hand-read, `research-notes.md` still separates verified fact from domain
knowledge, cites each claim to a node or a file path, and flags what could not be confirmed. A code
graph closes the "never infer from an absent grep" gap directly: before asserting something is absent,
confirm the graph could have shown it.
