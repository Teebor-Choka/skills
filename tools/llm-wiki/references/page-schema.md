# Page schema

Every `wiki/**/*.md` opens with this YAML frontmatter. It is the contract the CI enforces, so
keep the required keys present and the enum values valid:

```yaml
---
title: Human Readable Title
type: source-note | concept | entity | moc | synthesis | topic
domain: <first subdirectory under wiki/>
tags: [tag1, tag2]
source: <url / "Author Name" / "original">
date: YYYY-MM-DD
status: raw | summarized | synthesized
related: ["[[Page-Slug]]"]
conflicts: true # optional — present only when a "Conflicting Views" section exists
---
```

| `type`        | Purpose                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `source-note` | Distilled notes from one external source (book, article, video, email).                                                                     |
| `concept`     | A framework, idea, or technique that recurs across sources.                                                                                 |
| `entity`      | A named person, company, product, or book with its own identity.                                                                            |
| `moc`         | Map of Content — one per area (filename `_MOC.md`), the area's hub.                                                                         |
| `synthesis`   | Cross-source essay written from first principles. Original, uncited content is honest here.                                                 |
| `topic`       | Atomic hub aggregating claims across source notes, each cited inline via a wikilink. Ends with `## Sources in This Wiki` and `## See Also`. |

`status` tracks how far a page has moved from raw capture to connected knowledge: `raw`
(captured, maybe a stub pointing at `raw/`) → `summarized` (clean single-source notes) →
`synthesized` (cross-linked into the graph).

**Filenames** are lowercase `kebab-case.md`; the human title lives in `title:`. **Links** use
`[[Page-Slug]]` in the body and go into the `related:` array too. Links resolve by basename —
the path prefix is ignored — so a page can move between folders without breaking inbound links.
