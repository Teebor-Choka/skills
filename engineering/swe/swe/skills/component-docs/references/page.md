# Writing a page

Schema, section order, limits and validator rules: the contract in the docs tooling. The facts
you need while writing:

- Frontmatter keys are fixed. `updated` is today's date. `depends-on` is derived from manifests.
- Sections, in order: Purpose, Structure, Public API, Interactions, Flow, Decisions.
- At most 200 lines and 12 KB; aim for under 100.

| Section      | Write                                                                                               |
| ------------ | --------------------------------------------------------------------------------------------------- |
| Purpose      | One paragraph, present tense: what the component is for and for whom.                               |
| Structure    | Internal modules in a table (module, role). Stop at module level.                                   |
| Public API   | Items exported at the root or entry point that a caller uses, at most 25 rows. Link generated docs. |
| Interactions | What it calls and what it exposes: files, sockets, processes, environment. No "used by".            |
| Flow         | One mermaid block: the top-level flow through the component.                                        |
| Decisions    | Decisions in force, `**<decision>.** <reason>`. Current state only.                                 |

Rules that the validator cannot check:

- Name only items that exist in the code; the validator confirms each identifier occurs under `path`.
- Do not copy signatures or restate function bodies. Say what an item is for.
- A diagram shows the real flow you traced, not the module list.
- Decisions: delete a bullet when it stops being true. Keep a rejected alternative as a footnote
  only while it still explains the current choice.
- Never create a page for a component the resolver does not list.
