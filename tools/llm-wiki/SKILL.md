---
name: llm-wiki
description: >
  Build, grow, and query a personal knowledge wiki that an LLM can navigate: a linked graph of
  Markdown pages where every claim cites its source, so answers come from reading and following
  links, not from guessing. Use whenever the user wants to turn a folder of notes into a wiki;
  ingest a source (article, book notes, video transcript, PDF, raw dump) into an existing one;
  answer a question by querying the wiki; or lint it for broken links, orphan pages, stale
  claims, or missing cross-references. Trigger on "knowledge base", "second brain", "notes
  graph", "Obsidian vault", "Zettelkasten", "personal wiki", "digest my notes", "what do my
  notes say about X", or "keep my wiki healthy" — not only the exact phrase "LLM wiki". Do not
  use for codebase or repo knowledge graphs (use a code-aware tool), for hosted API/library
  documentation, or for a one-off answer the user does not want persisted.
---

# LLM Wiki

A knowledge graph where every claim cites its source and every page is machine-navigable, so an
LLM answers questions by reading the index, following links, and synthesizing — never by
inventing content. The conventions below exist to keep that guarantee true as the wiki grows.

## Repository layout

```
<repo>/
├── CLAUDE.md      ← agent instructions (bootstrap generates it, pointing back here)
├── index.md       ← one-line catalogue of every page, grouped by area
├── log.md         ← append-only chronological record of all operations
├── wiki/          ← LLM-owned knowledge layer (create and edit everything here)
├── raw/           ← immutable source material (READ, never modify)
│   ├── assets/    ← images (png/jpg/gif)
│   └── *.md/.txt  ← large clippings, raw dumps
└── resources/     ← non-knowledge artifacts (ignore during normal operations)
    └── attachments/
```

**Ownership** — the split keeps sources trustworthy and the graph malleable:

- `wiki/` — own it entirely. Create, edit, rename, link, merge pages freely.
- `raw/` — read-only. Cite it via the `source:` key; never edit, so the record of what a source
  actually said stays intact.
- `resources/` — ignore during normal operations.
- Root meta (`CLAUDE.md`, `index.md`, `log.md`) — keep current; update on every operation.

## Areas

The top level of `wiki/` is a set of thematic **areas** (Business, Marketing, Psychology, …).
Each area has one `_MOC.md` (Map of Content) — its hub — and every page in the area must be
linked from it. Sub-topic folders below are for human browsing only: CI ignores them, because
`domain:` is defined as the **first subdirectory under `wiki/`**, whatever the nesting depth. A
page at `wiki/Psychology/relationships/likeability.md` has `domain: Psychology`.

When bootstrapping, infer areas from the content. A common starting taxonomy is Business,
Marketing, Philosophy, Psychology, Communication, Finances, Technology, Life, Reference — add or
drop areas to fit. Keep the count in the 4–10 range so the index stays scannable.

## Page schema

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

## Two correctness rules

These are what make the wiki safe to trust; do not relax them.

**No fabrication on `topic` pages.** Every claim on a `type: topic` page must be attributed to a
source note via an inline `[[wikilink]]`; direct quotes go in quotation marks. Never invent or
paraphrase a claim without a citation. If a claim has no source note behind it, either omit it
or write it on a `synthesis` page (which is openly uncited) instead.

**Flag conflicts, don't resolve them.** When a `topic` page carries claims from two or more
sources that directly contradict each other, add a `## ⚠ Conflicting Views` section before
`## Sources in This Wiki`, list each position as a bullet attributed to its source, and add
`conflicts: true` to the frontmatter. State the positions with no editorial verdict. Only flag a
conflict traceable to source notes actually on disk — if it is not, record the gap in `log.md`
rather than fabricating one.

## Operations

Each operation ends by updating the meta files and running the CI, so the graph and its
catalogue never drift apart. Append a `log.md` entry every time.

### BOOTSTRAP — new wiki from scratch

Bootstrapping a new wiki from scratch (create dirs, install the CI hook, seed areas/meta): read
references/templates.md.

### INGEST — add a new source

1. Read the source from `raw/` (or a file the user provides). Discuss takeaways if they are
   present.
2. Create the page (`source-note`, with the raw file in `source:`) or update an existing one.
3. Update every **entity and concept page** the source touches — this is where the graph gains
   value; skipping it leaves the source stranded.
4. Add `[[wikilinks]]` to related pages and update their `related:` arrays.
5. Add the page to `index.md`; link it from its area `_MOC.md` under the right sub-theme.
6. Run `bash .ci/check-all.sh`, fix failures, then log `ingest`.

### QUERY — answer a question

1. Read `index.md` to find candidate pages; read the relevant `_MOC.md` hubs and drill in.
2. Synthesize an answer with `[[wikilink]]` citations.
3. If the answer is substantive (a comparison, analysis, or framework), **file it back** as a
   `synthesis` or `concept` page so explorations compound instead of evaporating.
4. Log `query`.

### LINT — health-check the graph

Run periodically or on request. Hunt for: contradictions between pages (flag, note which is
newer); stale claims superseded by newer sources (mark `status: raw` with a note); orphans (not
in any `_MOC.md`); missing concept pages (a term in 3+ pages with no page of its own); absent
cross-references; verifiable data gaps; and non-atomic `topic` pages that should be split. Then
log `lint` with a summary of findings.

## Atomicity

Each `topic` page should cover exactly one coherent concept. When a page grows past ~150 lines
or accretes sections that belong to different areas, split it: extracted sections become new
pages in their correct area, the original keeps the core concept, and both link back via
`## See Also`. Atomic pages are what make link-following a precise retrieval mechanism rather
than a scan of long documents.

## CI invariants

`bash .ci/check-all.sh` (scripts in `assets/ci/`) enforces five invariants; run it before every
commit and install it as the pre-commit hook so it runs automatically:

1. **check-frontmatter** — every `wiki/**/*.md` has the required keys and valid `type`/`status`.
2. **check-links** — every `[[wikilink]]` resolves to a real page (by basename).
3. **check-orphans** — every page is linked from its area's `_MOC.md`.
4. **check-layout** — `wiki/` holds only `.md` files; no `unsorted/` directory.
5. **check-log** — `log.md` has at least one entry matching `## [YYYY-MM-DD] op | subject`.

## Scaling with subagents

Scaling with subagents (parallel ingestion, multi-hop verify): read references/cross-agent.md.

## References bundled with this skill

- `references/templates.md` — copy-paste `_MOC.md`, `index.md`, and `log.md` skeletons. Read
  when bootstrapping or adding a new area or log entry.
- `references/moc-examples.md` — what a good area hub achieves and the shaping decisions with
  their criteria (an interface, not a sample to copy). Read when unsure how to shape an area hub.
- `references/cross-agent.md` — per-agent dispatch for the optional subagent workflows above.
  Read only when parallelizing ingestion or running a verification pass.
- `assets/ci/` — the complete CI shell scripts, ready to copy into a new repo.
