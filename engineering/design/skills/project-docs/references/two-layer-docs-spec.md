# Two-layer docs: format spec

Status: **P1, P2 and the validator half of P3 built, P4 to P6 proposed.** [`contract.md`](contract.md#components)
governs what is built: the component definitions, resolver, page template, validator rules and the
renderer ([generated files](contract.md#generated-files)). This file keeps what is not built yet.
SKILL.md does not link it, so a session using the skill does not act on it.

Covers Teebor-Choka/skills #107, #135 and #138. Extends [`contract.md`](contract.md),
[`flow.md`](flow.md), [`enforcement.md`](enforcement.md) and [`diagrams.md`](diagrams.md); it restates
none of them. Path rationale: `references/` is where the skill keeps its contract-level docs, and
the spec becomes contract text section by section as each phase lands, after which this file is
deleted.

## Layers and ownership

| Layer     | Docs                                                          | Authoring skill                    | Contract and enforcement |
| --------- | ------------------------------------------------------------- | ---------------------------------- | ------------------------ |
| Project   | `docs/overview.md`, `spec.md`, `process.md`, `decisions/`     | `design:project-docs`              | `design:project-docs`    |
| Component | `docs/components/<component>.md`, one page per component      | the document skill (new)           | `design:project-docs`    |
| Generated | `docs/generated/architecture.md`, `docs/generated/index.html` | none (written by `render_docs.py`) | `design:project-docs`    |

- **`design:project-docs` stays in `design` under its current name** (resolves #135 and #138 without
  a move). It owns design records: the overview, the architecture and the ADRs, the same artefacts
  `architect` produces forward and this skill records as built. Sessions, hooks and other skills
  already invoke `design:project-docs`, so a move would break each caller for no gain in behaviour.
- **The document skill is authoring only.** It explores code and writes component pages; it is
  engineering work done next to the code change, so it sits in `swe`. The component contract, the
  component resolver, the validator rules and the renderer stay in `project-docs`, which keeps one
  contract for both layers and the same authoring/enforcement split the skill already has.

## Definitions

Component, component name, internal dependency and page name: see
[`contract.md`](contract.md#definitions).

## Valid inputs

1. **Adoption.** Built in P1: component rules apply only where `docs/components/` exists. From P3 on
   (once the document skill can write the pages), the validator shall also emit
   `components-not-adopted` when the repo resolves to two or more components and the policy key
   `docs.components.adopt` is not `false`, so the layer cannot be skipped by omission. That rule
   turns existing conformant monorepos red, so it ships as a major version of the `design` plugin.
2. **Component resolution, page, single-component repos.** Built in P1: see
   [`contract.md`](contract.md#components).
3. **Changed-file set** (renderer trigger and `--pr-summary`). Built in P2: see
   [`contract.md`](contract.md#generated-files).

## Expected outputs

Built in P2, see [`contract.md`](contract.md#generated-files): the generated files, `--check`,
`--pr-summary`, the exit codes, the diff base and the update trigger (warn mode by default). The
`checks.<system>.project-docs-render` Nix derivation has no `.git` in its sandbox, so it checks drift
only (`--check --no-trigger`); the trigger runs in the pre-push hook and CI (P4).

## Update trigger promotion

**Promotion rule.** The default mode is `warn` (`--trigger warn`, policy key
`docs.components.trigger`). `render_docs.py --trigger-audit <rev-range>` replays the trigger over
merged first-parent commits and lists every hit with no page change. The owner labels each hit a
false positive or a missed update. The default flips to `fail` in a minor release of project-docs
when at least 30 labelled hits exist across adopting repos and false positives are at most 10% of
them. After the flip, the trailer is the only bypass and stays visible in `git log`.

## Staleness story

| Drift                             | Caught by                                                                                          |
| --------------------------------- | -------------------------------------------------------------------------------------------------- |
| generated files vs sources        | `--check` in pre-push and CI                                                                       |
| wiring (internal deps)            | `component-deps` against manifests; "used by" and the dependency graph are derived, never authored |
| component added, removed or moved | `component-missing`, `component-unknown`                                                           |
| public API removed or renamed     | `component-api-unknown`                                                                            |
| public API added, wiring changed  | the update trigger                                                                                 |
| flow or a decision no longer true | review (a staleness angle); not mechanical                                                         |

## Performance and scale

Target repos: up to 500 markdown files under `docs/`, 200 components, 2 MB of docs, diffs up to
10 000 changed lines. P2 measures `render_docs.py` against it (see the PR); `validate_docs.py` with
component rules stays under 3 s at that size.

## Dependency behaviour

| Dependency            | Assumed to guarantee                                  | If it does not                                                                                          |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| GitHub                | renders mermaid in `.md` files and PR bodies          | `architecture.md` stays readable as source                                                              |
| jsDelivr              | serves the pinned mermaid build matching the SRI hash | `index.html` shows the mermaid source unrendered; no fallback fetch                                     |
| Formatter (prettier)  | leaves `docs/generated/` alone                        | `--check` drifts forever; `install_hook.sh` prints the treefmt/prettier exclude for `docs/generated/**` |
| `design:project-docs` | installed beside the document skill                   | document HALTs `needs-input`, field `project-docs`, supply `--project-docs <dir>`                       |

## Assumptions

- **A1.** One page per component is enough. A module gets its own page only when it is declared a
  component through `docs.components.include`; the resolver never splits a crate into modules by
  itself (open question 1).
- **A2.** Normal internal dependencies are acyclic in every supported ecosystem when dev and build
  dependencies are excluded.
- **A3.** The prototype renderer exists only in feature worktrees of one downstream project
  (`scripts/render_docs.py`), not on its `main`. Its `FIXED_ORDER` hardcodes that project's
  `docs/architecture/` layout. P2 wrote the renderer from this spec and copied none of it.
- **A4.** Committed generated files conflict on parallel docs PRs; the resolution is rebase and
  re-render (#107 open question, option "accept and rebase").

## Out of scope

- API reference generation (rustdoc, typedoc): already a separate generated track per `diagrams.md`.
- Pages below component level, call graphs, data-flow graphs: they change every commit.
- A bot that commits regenerated files to PR branches: needs write tokens in CI; rebase is enough.
- A claude.ai artifact copy of `index.html`: it cannot be produced from CI (#107 open question).
- Pages for components in other repos, and decision history: git holds history.
- Moving `project-docs` to another plugin: decided against (see "Layers and ownership").

## AI-gap self-test

_If an agent built this, passed all tests, but behaved wrong, what did I miss?_ Each answer is a constraint in this spec or in
[`contract.md`](contract.md#components).

| Miss                                                               | Constraint                                                                                     |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Output byte-identical on the CI box, different on a laptop         | codepoint sort, POSIX relpaths, LF, no locale; tests shuffle file order and set a non-C locale |
| Prettier rewrites `architecture.md`, `--check` never passes        | formatter exclude printed by `install_hook.sh`; acceptance test runs the formatter             |
| Agent invents components for an unsupported workspace format       | `needs-input` exit 3, never a directory-tree guess                                             |
| Page restates the code (80-row API table)                          | root-exported items only, 25 rows, 200 lines                                                   |
| Decisions section turns into a changelog                           | current state only; delete stale bullets; history is git                                       |
| Trigger fires on every formatting change, gets ignored             | `git diff -w`, test paths excluded, warn mode until measured                                   |
| `index.html` fails the project's own validator                     | `docs/generated/` exempt from view rules, stated in contract                                   |
| `--pr-summary` link 404s                                           | warn when `HEAD` is unpushed; non-GitHub fallback                                              |
| Hand-written `depends-on` drifts from `Cargo.toml`                 | `component-deps` checks it against manifests                                                   |
| A mermaid label with `<` breaks the HTML page                      | HTML-escape every interpolated string; fixture covers it                                       |
| Trigger satisfied by bumping `updated:` on the page                | only a body change counts                                                                      |
| Trigger silently passes in a shallow CI clone                      | an explicit `--base` that does not resolve exits 2                                             |
| P1 turns every conformant monorepo red before pages can be written | component rules gated on `docs/components/`; `components-not-adopted` waits for P3, major bump |

## Work breakdown

| Phase | Deliverable                                                                                                                                                                                                       | Plugin, version                        | Acceptance     |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | -------------- |
| P2    | `scripts/render_docs.py` (both layers, `--check`, `--pr-summary`, trigger in warn mode, `--trigger-audit`)                                                                                                        | design, minor                          | AT-11 to AT-25 |
| P3    | the document skill: explore, write pages, `needs-input`, `--interactive`; validator rule `components-not-adopted`                                                                                                 | swe, minor; design, major; marketplace | AT-26 to AT-30 |
| P4    | `install_hook.sh` pre-push render check and formatter exclude; Nix `checks.<system>.project-docs-render` (drift only); `AGENTS.pointer.md` mandatory line; `flow.md` render step after validate; `enforcement.md` | design, minor                          | AT-31 to AT-35 |
| P5    | `engineering/tools/git/skills/workflow` PR conventions: paste `--pr-summary` when `docs/**/*.md` changes                                                                                                          | git, patch                             | AT-36          |
| P6    | Trigger promotion: run the audit, label hits, flip default when the rule holds                                                                                                                                    | design, minor                          | AT-37          |

P2 is built: `scripts/render_docs.py` and `tests/test_render_docs.py`; the text moved into
[`contract.md`](contract.md#generated-files) and [`flow.md`](flow.md#finish).

P1 is built: `contract.md` component section and `docs/generated/` carve-out, `scripts/components.py`,
the validator rules, `assets/component.skeleton.md` and fixtures. Its acceptance tests AT-1 to AT-10 are
`tests/test_components.py` and `tests/test_component_pages.py`; the resolver half of AT-25 (`tomllib`
imported only for a TOML manifest) ships with them.

The `AGENTS.pointer.md` mandatory line (P4): _Whenever `docs/**/*.md` changes, run
`render_docs.py`, commit `docs/generated/*`, and paste `render_docs.py --pr-summary` into the PR
description. The pre-push hook and CI enforce the render._

## Proposed acceptance tests

Proposed, not final; the owner derives the final list. Numbers are kept so AT-11 onward stay stable.

P1 (AT-1 to AT-10) is built; see the tests named under "Work breakdown".

P2 (AT-11 to AT-25) is built; see `tests/test_render_docs.py`. AT-18 is checked there only where
prettier is installed; the formatter exclude itself is P4 (AT-34).

P3, the document skill:

26. Run non-interactively on a fixture workspace: one conforming page per component, validator clean.
27. Unsupported workspace: the skill returns the `needs-input` result unchanged and writes nothing.
28. Without `design:project-docs` present: `needs-input` with field `project-docs`.
29. Adversarial: a page for a component the resolver does not list is never created.
30. Two-crate repo, no `docs/components/`, no policy key: `components-not-adopted`; with `docs.components.adopt: false`: none.

P4, wiring:

31. `install_hook.sh` on a plain-hooks repo adds a pre-push render check, idempotent on re-run.
32. On a pre-commit-framework repo it prints the stanza and edits nothing.
33. On a flake repo it prints `checks.<system>.project-docs-render`, and `nix flake check` fails on drift with no `.git` in the sandbox.
34. It prints the formatter exclude for `docs/generated/**`.
35. `AGENTS.pointer.md` contains the mandatory line; `flow.md` lists render after validate.

P5 and P6:

36. The git workflow skill's PR conventions name `--pr-summary` for PRs touching `docs/**/*.md`.
37. `--trigger-audit` over a known range lists exactly the expected hits; the flip ships only with the labelled count recorded in the PR.

## Open questions

Each has a recommended default; the spec above assumes the default. The owner approved the defaults of
questions 1 to 3; both are now in [`contract.md`](contract.md#components) (1, 2) or in the update trigger (3).

1. **Modules as components.** Default: manifest members only, modules only when declared in
   `docs.components.include`.
2. **Rollout for existing monorepos.** Default: P1 rules gated on `docs/components/`;
   `components-not-adopted` lands with P3 as a major bump of `design`.
3. **Promotion numbers and labelling.** Default: 30 labelled hits, false positives at most 10%,
   the owner labels.
4. **Conflicts on committed generated files.** Default: rebase and re-render; no bot, no merge driver.
5. **Fail mode without a diff base.** Default: exit 1, so fail mode never passes by losing its base.
