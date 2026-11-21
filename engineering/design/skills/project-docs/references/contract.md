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
  process.md               # optional, for a project with an .agents/ process (see below)
  views/
    <name>.html            # optional, a rendered view of docs/<name>.md (see "Views")
  components/
    <name>.md              # optional layer, one page per component (see "Components")
  generated/               # written by tools, never by hand (see "Generated files")
  decisions/
    README.md              # required: the index
    <slug>.md              # one ADR per decision, >=1
AGENTS.md                  # required: points into docs/
```

- `overview.md` and `decisions/` (index + at least one ADR) are **always** required.
- `spec.md` is **opt-in by size**: required only when the project has real behavior to specify (a
  pipeline, a protocol, stateful subsystems). A trivial project (a static page, a docs-only or
  notes-only effort) omits it. See "Spec opt-in" below. When present, it must conform.
- `process.md` is **optional**: a project with no defined process omits it. See "Process doc" below.
  When present, it must conform.
- `components/` is the **component layer**. It is opt-in: a repo without `docs/components/` is checked
  by the rules above and no others. See "Components".
- A project may keep extra docs (`design/`, `providers/`, `architecture/`); the contract neither
  requires nor forbids them, and the validator ignores them.

## Frontmatter

Every doc under `docs/` starts with YAML frontmatter, except `docs/generated/`. Keys per kind:

| File                  | `kind`            | required keys                           | optional keys                 |
| --------------------- | ----------------- | --------------------------------------- | ----------------------------- |
| `overview.md`         | `overview`        | `title`, `kind`, `project`, `updated`   | none                          |
| `spec.md`             | `spec`            | `title`, `kind`, `project`, `updated`   | none                          |
| `process.md`          | `process`         | `title`, `kind`, `project`, `updated`   | none                          |
| `decisions/README.md` | `decisions-index` | `title`, `kind`, `project`, `updated`   | none                          |
| `decisions/<slug>.md` | (ADR, no `kind`)  | `title`, `status`, `project`, `updated` | `supersedes`, `superseded-by` |
| `components/<n>.md`   | `component`       | see "Components"                        | none                          |

- `title`: non-empty string.
- `project`: the project's short name; the same value across every doc in that project. `repo` is
  accepted as a deprecated alias (the validator reads it but prefers `project`).
- `updated`: an ISO date `YYYY-MM-DD`.
- `status` (ADR only): one of `proposed`, `accepted`. Only active decisions get a file (see below).

## ADR structure

`decisions/` holds only **active** decisions: one file per decision in force. A decision that was
denied or later discarded does not get its own file; fold it as a footnote into the active decision
it bears on. This keeps the set compact (what is true now), with the history attached where it is
read.

Each `decisions/<slug>.md`:

- Filename `<slug>` is kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`), naming the decision, not numbered.
  Renaming is cheaper than renumbering, and the index carries the order.
- Body contains three section labels, in order: **Context**, **Decision**, **Consequences**. House
  style writes them as bold leads (`**Context.** ...`); `## Context` headings also pass.
- A denied or discarded alternative is recorded as a **Markdown footnote** on the active decision,
  not as a separate record or a standalone section: `... SQLite [^pg]` with a matching `[^pg]:
Postgres was considered and dropped because ...` below. The footnote preserves why the alternative
  lost, so it is not re-proposed without new information. Every footnote reference must have a
  matching definition; the validator checks that.

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

| Doc            | Mandatory                                                  |
| -------------- | ---------------------------------------------------------- |
| `overview.md`  | at least one mermaid block (the context or component view) |
| `spec.md`      | at least one mermaid block (a subsystem view)              |
| `process.md`   | at least one mermaid block (the process)                   |
| component page | at least one mermaid block (the flow)                      |
| ADRs           | none (add one only where the decision is structural)       |

The validator checks presence of a non-empty mermaid block, never correctness. "A diagram per subsystem" in `spec.md` and the
choice of form (flowchart, sequence, state, DAG) are standards in `diagrams.md`, enforced by review,
not the script. Code-level graphs (API surface, call/data-flow) are a separate generated track and
are **not** authored into `docs/`; link to them instead.

## Process doc

A project can define its process as documents: `.agents/policy.md` and the workflow files it runs.
`docs/process.md` tells a reader of `docs/` which workflows the project runs, where their documents
live, and who decides what.

- `docs/process.md` is optional. The validator checks only that it conforms: valid frontmatter,
  `kind: process`, and a diagram. It does not read `.agents/` or validate a workflow; the workflow's
  own tooling does that.

## Views

A view is a rendering of one markdown doc for a reader who wants to see it, not read it: a flow, a
table, a card grid. `docs/views/<name>.html` renders `docs/<name>.md`. The markdown stays the source
of truth; the view is optional and never required.

The stack is one HTML file with inline CSS: no script, no network, no build step, so it renders the
same in any browser, offline, in print, and in a harness with no hosted tooling. A hosted page
(an artifact, a doc) may be made from the same file, but nothing here depends on one.

When `docs/views/` exists, each `*.html` in it must have:

- a non-empty `<title>` and a `<meta name="viewport">`;
- `<meta name="source" content="docs/<name>.md">`, where `<name>` is the view's own file name and the
  file exists (`view-source`);
- `<meta name="updated" content="YYYY-MM-DD">`, equal to the `updated` in the source's frontmatter,
  so a view that fell behind its source fails (`view-updated`). A source with no `updated` has
  nothing to compare, so the date is only checked as a date;
- no script and nothing loaded from outside the file (`view-external`): no `<script>`, no `on*`
  handler, no `srcdoc`, no `javascript:` link. Any attribute that names a resource (`src`, `poster`,
  `data`, `action`, `formaction`, `href` and `xlink:href` on any tag but `<a>`, and every `srcset`
  candidate) must be a `data:` URI or a `#fragment`. In CSS, no `@import` or `image-set()`, and
  `url()` only with `data:` or `#fragment`; CSS comments are ignored. A plain `<a href>` is
  navigation and passes. Meta names are case-insensitive;
- a `@media (prefers-color-scheme: dark)` rule (`view-theme`).

The validator also scans views for credential-shaped strings. It does not check that the view says
what its source says; the authoring flow and review do.

## Components

The component layer documents each crate, package or module that has a public API, one page each.
`design:project-docs` owns the contract and the validator rules; the pages are written next to the code
change. Every page rule in this section is active only where `docs/components/` exists.

A repo that resolves to one component needs no page, because the project layer covers it; a page
that exists anyway must conform. A repo that resolves to two or more components and has no
`docs/components/` fails `components-not-adopted`, so the layer cannot be skipped by omission. Opt out
with `docs.components.adopt: false` in the policy.

### Definitions

- **Component**: a crate, package or module with a public API. Two sources:
  - **Manifest members** (default): a Cargo workspace member, an npm/yarn workspace package, a uv
    workspace member or the single `pyproject.toml` package, a Go module in `go.work` or the single
    `go.mod`.
  - **Declared directories**: directories matched by the `docs.components.include` globs, for
    example `crates/widget/src/*/` in a single crate. The resolver never picks modules on its own,
    because which modules carry a public API is a judgment call. A matched directory with a manifest
    is read as a manifest member; one without is a module named by its directory.
- **Component name**: the manifest's package name (`[package].name`, `package.json` `name`,
  `[project].name`, the last segment of the Go module path); for a module, its directory name.
- **Internal dependency**: a normal (non-dev, non-build) dependency on another component of the same
  repo. Dev, build, optional-group and `devDependencies` entries are not edges, so the graph stays
  acyclic.
- **Page name**: `docs/components/<name>.md`, where `<name>` is the component name with each
  character outside `[a-z0-9-]` replaced by `-`.

### Resolver

`scripts/components.py [project] [--components GLOB ...] [--interactive]` resolves the component set
with the standard library only. It expands workspace globs with `fnmatch` over directory names,
honours Cargo `exclude` and npm `!` patterns, and sorts the result by codepoint of the POSIX relpath.
`tomllib` is imported only to parse a TOML manifest; on Python below 3.11 that exits 2 with
`python 3.11+ required to parse <file>`. A manifest that does not parse, or two components with one
name, also exit 2 and name the file.

Policy keys come from the project's own `.agents/policy.md` (the global layer is not read), in the
shared policy format: maps by indentation, inline lists, no block lists.

```yaml
docs:
  components:
    include: ["crates/widget/src/*/"] # replaces manifest discovery; --components does the same
    exclude: # name: reason, removes a member and its edges
      widget-test-kit: test helper, no public API
    adopt: false # only to opt out of components-not-adopted; any other value, or none, expects pages
```

If the repo has a workspace format the resolver cannot parse (`pnpm-workspace.yaml`, Bazel,
a Gradle multi-project) and no include list is set, it **halts**: one JSON object on stdout, exit 3,
and no default is substituted.

```json
{
  "status": "needs-input",
  "tool": "components.py",
  "missing": [
    {
      "field": "components",
      "reason": "pnpm-workspace.yaml is not parseable with the Python stdlib",
      "supply": [
        "--components 'packages/*'",
        ".agents/policy docs.components.include"
      ]
    }
  ]
}
```

The run never prompts. `--interactive` turns the same list into questions on stderr; stdout stays
JSON. Exit codes: 0 resolved, 2 unreadable input, 3 needs-input. A repo with no manifests resolves
to an empty set.

### Component page

Frontmatter is flat; keys are all required:

| Key          | Value                                                                             |
| ------------ | --------------------------------------------------------------------------------- |
| `title`      | the component name                                                                |
| `kind`       | `component`                                                                       |
| `project`    | same value as every other doc in the project                                      |
| `updated`    | `YYYY-MM-DD`                                                                      |
| `component`  | the manifest package name, exactly                                                |
| `path`       | repo-relative POSIX dir of the manifest                                           |
| `depends-on` | `[a, b]` internal dependencies by component name, codepoint-sorted; `[]` for none |

Sections, as `##` headings in this order: **Purpose**, **Structure**, **Public API**,
**Interactions**, **Flow**, **Decisions**. `assets/component.skeleton.md` is the starting shape.

- **Purpose**: one paragraph.
- **Structure**: how the component is assembled, internal modules in a table (module, role). Stops at
  module level; no per-function detail ([`diagrams.md`](diagrams.md), two tracks).
- **Public API**: a table of the entry points a caller uses (item, what it does). Only items exported
  at the component's root or entry point, at most 25 rows; link generated API docs for the rest.
- **Interactions**: what it calls and what it exposes to the outside (files, sockets, processes,
  env). `depends-on` carries the internal edges; "used by" is never authored.
- **Flow**: the top-level flow through the component, as one mermaid block (`sequenceDiagram` or
  `flowchart`). At least one mermaid block on the page.
- **Decisions**: the decisions in force, one per bullet, `**<decision>.** <reason>`. **Current state
  only.** When a decision stops being true, delete the bullet; git history keeps the past. A rejected
  alternative stays as a footnote only while it still explains the current choice. A decision that
  binds more than this component moves to `docs/decisions/` as an ADR and the bullet links it.
  Review checks this rule; the validator cannot.

Size: at most 200 lines and 12 KB including frontmatter; target under 100 lines.

A worked example, `sandy-fsutil` (facts from a real Rust workspace at one commit), is the validator's
test fixture: `tests/fixtures/sandy-fsutil/docs/components/sandy-fsutil.md`.

### Component rules

Each is a finding with exit 1, per [Severity](#severity-and-exit-code).

| Rule                     | Fires when                                                                                                                                                                        |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `component-frontmatter`  | no frontmatter, a key missing or empty, `kind` not `component`, bad `updated`, `depends-on` not a list                                                                            |
| `component-sections`     | a section heading is missing, or the six are out of order (headings inside code fences do not count)                                                                              |
| `component-mermaid`      | no non-empty mermaid block on the page                                                                                                                                            |
| `component-size`         | over 200 lines, over 12 KB, or a Public API table over 25 rows                                                                                                                    |
| `component-missing`      | a resolved component has no page and no `exclude` entry (not checked when there is one component)                                                                                 |
| `component-unknown`      | a page's `component` and `path` match no resolved component                                                                                                                       |
| `component-deps`         | `depends-on` differs from the manifest's internal dependencies (not checked for declared modules)                                                                                 |
| `component-api-unknown`  | an identifier in the Public API table's first column occurs as a whole word in no file under `path`                                                                               |
| `components-not-adopted` | two or more components resolve and `docs/components/` does not exist; skipped when `docs.components.adopt` is `false`, the workspace cannot be read, or `components.py` is absent |
| `components-unresolved`  | the resolver halts with needs-input; the message names the same supply options                                                                                                    |

For `component-api-unknown`, each code span in the cell is split on `::`, `{`, `}`, `,` and
whitespace, and every non-empty token is an identifier, so `OwnedDir::{open, open_or_create}`
yields `OwnedDir`, `open`, `open_or_create`. The scan skips the project's `docs/`, `.git`,
`node_modules`, `target` and similar build directories, so a page cannot satisfy itself.

Component pages also take part in the whole-project checks: `project-divergence` and
`secret-pattern`. The validator loads `components.py` from beside itself, and only when
`docs/components/` exists; a copy of `validate_docs.py` on its own exits 2 there, naming the file.

### Generated files

`docs/generated/` holds files written by tools and never edited by hand. The validator skips
frontmatter, view and size checks there, and the [Views](#views) no-script rule does not apply to it.

`scripts/render_docs.py [project]` writes `docs/generated/architecture.md` and
`docs/generated/index.html`, byte-identical for identical input. It needs Python 3.9+; below that it
exits 2 naming the interpreter version. Rendering reads no manifest, so it needs no `tomllib`.

- **Order.** Project layer first: `overview.md`, `spec.md`, `process.md`, then other `docs/**/*.md`
  outside `components/`, `generated/` and `decisions/` by codepoint of relpath, then `decisions/*.md`.
  Component layer second: a `flowchart` of the `depends-on` graph, then each page, dependencies first,
  ties by codepoint of the component name. Each layer opens with a labelled heading (`Project`,
  `Components`). A repo with no component pages has no `Components` layer.
- **Per diagram**: the section heading (the document title when none precedes it), the first paragraph
  of the section (at most 400 characters), the mermaid source, and a relative link to the source
  heading. **Per component** also the Purpose paragraph and a derived `Used by:` line.
- **Determinism**: no clock, no absolute path, no locale-dependent sort, LF newlines, UTF-8, one
  trailing newline. A mermaid fence is one backtick longer than the longest backtick run inside it.
- **`architecture.md`** opens with `<!-- generated by render_docs.py; do not edit -->`.
- **`index.html`** is one file with light and dark theme. Each diagram scrolls inside its own frame.
  Mermaid loads from one pinned `cdn.jsdelivr.net` version with an SRI hash, and every interpolated
  string is HTML-escaped. Offline, the page shows the mermaid source unrendered.

| Command                        | Does                                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `render_docs.py`               | writes both files; nothing is written when any input fails                                           |
| `--check`                      | compares bytes with the committed files; exit 1 names each drifted file and the regenerate command   |
| `--check --no-trigger`         | drift only; needs no `.git` (the Nix check)                                                          |
| `--check --trigger warn\|fail` | adds the update trigger; the default is policy `docs.components.trigger`, else `warn`                |
| `--pr-summary`                 | prints a markdown block for the PR description (below)                                               |
| `--trigger-audit <range>`      | prints `<sha>\t<component>\t<files>` for each trigger hit over the first-parent commits of the range |
| `--base <ref>`                 | the diff base; CI passes the PR base SHA                                                             |

Exit codes: 0 ok, 1 drift or a trigger failure in `fail` mode, 2 unreadable input (an unterminated
fence, no `docs/`, an unreadable file, bad frontmatter on a component page, a `depends-on` cycle, an
explicit `--base` that does not resolve), 3 needs-input from the component resolver. Messages name the
file and line, or the cycle (`a -> b -> a`; the manifest decides, so fix the page's `depends-on`).

**Diff base.** The changed-file set is `git diff <base>...HEAD`, run in the project directory, so a
project below the repo root sees only its own paths. `<base>` is `--base <ref>` when given; else the
merge-base of `HEAD` with `@{upstream}`; else with `origin/HEAD`. An explicit `--base` that does not
resolve exits 2 in every mode (a shallow CI clone needs `fetch-depth: 0` or a fetch of the base SHA).
With no implicit base, the trigger prints `warning: trigger-skipped: no diff base` on stderr and exits 0
in `warn` mode and 1 in `fail` mode. Never a silent pass. The trigger runs only where
`docs/components/` exists.

**Update trigger.** For each component whose `path` holds a changed file (longest prefix wins), a
**surface change** is an added or removed line, found with `git diff -w` and ignoring files under
`tests/`, `benches/`, `examples/` and `*_test.*`, that matches:

| Ecosystem | Public surface                                                                                                                                           |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rust      | `^\s*pub\s+(fn\|struct\|enum\|trait\|type\|const\|static\|mod\|use)\b` (not `pub(crate)`, `pub(super)`, `pub(in ...)`)                                   |
| TS/JS     | `^\s*export\b`                                                                                                                                           |
| Python    | `__all__`, or a top-level `def`/`class` whose name has no leading `_`                                                                                    |
| Go        | a top-level `func`, `type`, `var` or `const` with an upper-case name                                                                                     |
| Wiring    | an edit in the component's own manifest on a line that names another component, other than a metadata key (`name`, `version`, `description` and similar) |

The language is taken from the file extension. A surface change is satisfied when the same range
changes the body of the component's page (frontmatter keys and whitespace do not count), or a commit
in the range carries `Docs-Unchanged: <component>: <reason>`; a trailer with no reason or another name
does not count. Otherwise stderr gets `warning: component-page-stale: <component>: <files>` (`error:` in
`fail` mode, which exits 1). Flow changes have no mechanical signal; the staleness angle in the review
plugin's `by-angle` skill covers them. The trigger resolves components with `components.py`, so it
inherits its needs-input halt (exit 3) and its `tomllib` rule (exit 2 naming the manifest on Python
below 3.11). The default mode stays `warn` until the promotion rule in the spec is met.

**PR summary.** `--pr-summary` prints one line linking `docs/generated/architecture.md` at the head
SHA, then the mermaid blocks of each changed `docs/**/*.md` (generated files excluded), each under
`#### <source path>: <heading>`. The link is
`https://github.com/<owner>/<repo>/blob/<sha>/docs/generated/architecture.md` when `origin` is a GitHub
URL (https or ssh), else `docs/generated/architecture.md @ <sha>`. When `HEAD` is on no remote-tracking
ref it warns on stderr that the link resolves only after push. A block over 60 000 characters drops
diagrams from the end and ends with `N more diagrams in architecture.md`. With no diff base it prints
the link alone and warns.

A formatter that rewrites `docs/generated/` makes `--check` drift for good; exclude the directory from it.

## Spec opt-in

A project needs `spec.md` when getting it wrong would cost something: it has a runtime pipeline, a
protocol or wire format, stateful subsystems, or non-obvious failure/recovery behavior. It does not
need one when the project is a static artifact, a thin wrapper, or pure documents. The author
decides at authoring time and records the call in `overview.md` (a one-line "no deep spec: REASON"
when omitted). The validator does not force `spec.md`; it only conforms one that exists.

## Severity and exit code

Every finding makes the exit code nonzero, including one labelled `warning` (for example
`undocumented`): the label is informational, not a pass. The validator also flags credential-shaped
strings in the checked docs (`secret-pattern`, a backstop only; it reports the file, never the
match) and `supersedes` / `superseded-by` keys that name no ADR in `docs/decisions`.

## What the validator does not do

It checks structure, not content quality or currency. A view's `updated` date can only prove the view
was re-dated, not that it was re-rendered. It cannot tell whether a diagram is accurate,
whether prose is terse, or whether an ADR is still true. Those are the authoring flow's job (write it
right) and the optional staleness review knob's job (catch it going stale).
