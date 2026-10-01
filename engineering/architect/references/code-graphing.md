# Grounding the current state with a code graph

Step 1 grounds what is actually true today. On anything larger than a small repo, a code graph
answers "what is here, what depends on what, what breaks if this changes" far faster and more
completely than reading and grepping by hand, and it is the first coherent way to describe how
_several_ repositories fit together. This file is how to ground through one, optionally, with a graceful
fall back to manual reading when no code-graphing tool is present.

The flow is: **determine scope → ensure a fresh index → explore → write research-notes**. Every claim
still traces to a node or a file path; anything the graph cannot resolve is flagged, not asserted.

## 1. Determine scope (which repos are the project)

- If the working directory is itself a repository, that is the default single-repo scope.
- If it is **not** a repository, or the scope is ambiguous, scan the current directory's immediate
  contents for candidate repositories (subdirectories that are git repos or code roots) and **ask the
  user two things**: (a) which of those repositories to include, and (b) what constitutes a _unit of
  project_ here, how the chosen repos group into one architecture (one service plus its libraries;
  several services that ship together; a frontend, backend, and infra set). Do not guess the grouping;
  it decides what "the system" means for the rest of the package.

## 2. Detect the capability

Prefer, in order, and use whichever is present:

1. **codegraph** (https://github.com/colbymchenry/codegraph, MIT): available when its MCP tools
   (`codegraph_explore`, `codegraph_node`) are exposed to the host, or the `codegraph` CLI is on PATH.
2. **graphify**: a future alternative; detect a `graphify-out/` index.
3. **none**: fall back to manual grounding (read the real repos and configs) and say so in
   `research-notes.md`, so a reader knows the floor was hand-built, not graph-derived.

The MCP tools and the CLI subcommands return the same output, so a host without the codegraph MCP uses
the identical CLI; the mapping below names both.

## 3. Ensure a fresh index (build the current state first)

Ground the _current_ code, not a stale snapshot. For each in-scope repo:

- Check `codegraph status --json`. It reports top-level `initialized`, `nodeCount`/`edgeCount`,
  `languages`, and `pendingChanges` (its `added` / `modified` / `removed` counts), plus a nested
  `index` object whose `index.reindexRecommended` flags a stale index.
- If `initialized` is false, build the index: `codegraph init <repo>`.
- If any of `pendingChanges.{added,modified,removed}` is non-zero, or `index.reindexRecommended` is
  true, refresh it: `codegraph sync <repo>` (codegraph's own file-watcher may already have synced;
  `status` confirms).

The index lives in a `.codegraph/` directory in the repo; it is disposable and must never be committed
(the repo `.gitignore` excludes it).

## 4. Ground through the graph, mapped to research-notes.md

| Question (research-notes section)                                 | codegraph capability                                                                                                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Current architecture, each subsystem with the file that proves it | `codegraph_explore "<area>"` (or `codegraph explore`): relevant symbols' verbatim source, call paths, and a blast-radius summary for that area                      |
| Dependencies and the blast radius of a change                     | `codegraph_node <symbol>` (or `codegraph node`): a symbol's caller/callee trail; `codegraph impact <symbol>` and `codegraph callers <symbol>` for a specific change |
| Where the code lives, the file structure                          | `codegraph files --json`                                                                                                                                            |
| Coupling hotspots (what to watch)                                 | the caller/dependent counts codegraph reports per symbol and file                                                                                                   |

Read the coupling counts as afferent (callers in) and efferent (callees out). The high-fan-in,
high-fan-out symbols and files are the hotspots. **Name the module and service boundaries yourself**
from that coupling plus the dependency edges, using the Ford and Richards coupling and quantum framing
in `principles.md`; codegraph reports the numbers, you make the architectural call. There is no
community-detection step.

## 5. Multi-repo (cross-repo architecture)

For a project that spans several repos: index and ground each repo, then describe the **cross-repo
picture**, which imports or calls cross a repo boundary, which repo owns which capability, and where
the seams are. codegraph resolves cross-file references and some cross-language bridges; where it
cannot resolve an edge, say so rather than asserting it. The cross-repo dependencies and the shared
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
confirm the graph could have shown it. The graph makes grounding faster and more complete; it does not
change what "grounded" means.
