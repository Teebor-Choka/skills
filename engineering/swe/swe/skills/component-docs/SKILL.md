---
name: component-docs
description: >
  Write or update a component page, under docs/components/, one per crate, package or module
  with a public API. Use when a change adds, removes or renames a public API item, changes how
  components are wired or the top-level flow, or when adding a component, or when asked to
  document the components of a repo. Not for the project overview, ADRs or API reference
  generation.
---

# component-docs

One page per component, written next to the code change that makes it true. The page is a
short map for the next reader: what the component is for, how it is built, what a caller uses,
how it behaves.

The docs tooling (contract, resolver, validator) lives outside this skill. `scripts/resolve.py`
finds it and runs its resolver; the contract is `references/contract.md` in that directory, and
the page skeleton is `assets/component.skeleton.md` there. This skill adds no rules of its own.

## Never ask

This skill runs with no one to answer. It never asks a question as a required step. When the
repo cannot supply an input, run `scripts/resolve.py` and read the result: exit 3 with
`"status": "needs-input"` means stop. Return that JSON unchanged to whoever started you, write
nothing, and do not guess a component set from the directory tree. See
[references/halting.md](references/halting.md).

## Write pages

1. Resolve: `python3 scripts/resolve.py <project>`. The component list in the result is the
   whole set; a directory not on it gets no page.
2. Scaffold: `python3 scripts/resolve.py <project> --scaffold` writes a skeleton for each
   component that has none, with `component`, `path` and `depends-on` filled from the manifests.
   It never overwrites a page. Do not hand-edit those three keys; change the manifest or the
   policy instead.
3. Explore the component's code (a code graph if one is available, else read the entry point
   and the module list) and fill the body from what you found. Describe what exists.
4. Run the tooling's validator on the project. Fix every finding.

Page shape, size limits and the section rules are in
[references/page.md](references/page.md). Keep the prose terse and plain.

## Update pages

A change obliges a page update when it adds, removes or renames an item in the Public API
table, changes the component's internal dependencies, changes the top-level flow, or makes a
decision in the Decisions section untrue. Change the page body in the same commit. Bumping
`updated` alone does not count.

When a change touches code but needs no page change, say so in a commit trailer:

```
Docs-Unchanged: <component>: <reason>
```

Details and what counts: [references/updating.md](references/updating.md).

## Decisions section

Current state only. One bullet per decision in force. When a decision stops being true, delete
the bullet; git history keeps the past. A decision that binds more than this component belongs
in the project's decision records, with a link from the bullet.
