# Shaping an area hub (`_MOC.md`)

What a good area `_MOC.md` achieves, and the decisions that shape one — an interface, not a sample
to copy. For the copy-paste frontmatter and section skeleton, see `templates.md`.

## What the hub is for

An area's `_MOC.md` is the entry point a query hits after `index.md`: from the hub alone a reader
should be able to pick which pages in the area are worth opening for a given question. It maps the
whole area onto one page so link-following starts from a complete, current picture — not a
guess about what the folder contains.

## Shaping decisions and their criteria

- **Coverage** — every page in the area is linked from exactly one sub-section of the hub. This is
  enforced: `check-orphans` fails if any page in the area is missing from its `_MOC.md`. One
  section per page, never zero and never two.
- **Ordering** — list entities and people first (their own `## Key Entities` section when the area
  has them), then the topic/concept/source sub-sections. A reader scanning for "who" finds them
  before the "what".
- **Sub-section names mirror the folder tree** — each `## Sub-topic` heading matches the name of a
  sub-topic folder under the area. The hub then reflects the on-disk structure, so a reader can
  map a section back to where its pages live.
- **Header page count** — the `**N pages**` count is the number of content pages in the area and
  **excludes the `_MOC.md` page itself**. It must match the actual count.
- **Breadcrumbs** — the header lists cross-referenced areas separated by `·` (e.g.
  `**N pages** · [[OtherArea/_MOC]] · [[ThirdArea/_MOC]]`).
- **See Also** — a closing `## See Also (other areas)` points to the areas that cross-reference
  this one, each with a one-line note on what the link is for. This is where cross-domain hubs
  declare which other areas reach into them.

## Done

The hub is done when:

- `check-orphans` and `check-links` both pass (every page covered exactly once; every link
  resolves), and
- a reader can pick candidate pages for a question from the hub alone — the one-liner on each
  entry says enough to decide whether to open it.

## Skeletal shape

Placeholders only — the real structure and one-liners come from the area's actual pages. For the
full frontmatter block, see `templates.md`.

```markdown
# <Area>

**N pages** · [[OtherArea/_MOC]] · [[ThirdArea/_MOC]]

---

## Key Entities

- [[entity-slug]] — one-liner _(entity)_

## <Sub-topic matching a folder name>

- [[page-slug]] — one-liner _(topic)_

---

## See Also (other areas)

- [[OtherArea/_MOC]] — what this cross-reference is for
```
