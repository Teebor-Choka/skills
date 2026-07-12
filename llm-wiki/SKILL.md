---
name: llm-wiki
description: >
  Create, maintain, and query a personal knowledge wiki designed to be navigated by LLMs.
  Use this skill whenever the user wants to: bootstrap a new LLM wiki from a folder of notes;
  ingest a new source (article, book notes, video transcript, raw file) into an existing wiki;
  answer a question by querying an existing wiki; or lint/health-check a wiki for broken links,
  orphan pages, stale claims, or missing cross-references. Trigger even when the user says
  "knowledge base", "second brain", "notes graph", "Obsidian vault", or "personal wiki" —
  not just the exact phrase "LLM wiki".
---

# LLM Wiki

A structured knowledge graph where every claim cites its source and every page is machine-navigable. Designed so an LLM can answer questions by reading the index, following links, and synthesizing — without hallucinating content.

---

## Three-layer structure

```
<repo>/
├── CLAUDE.md      ← agent instructions (this skill generates it on bootstrap)
├── index.md       ← one-line catalogue of every page, grouped by area
├── log.md         ← append-only chronological record of all operations
├── wiki/          ← LLM-owned knowledge layer (you create and edit everything here)
├── raw/           ← immutable source material (you READ, never modify)
│   ├── assets/    ← images (png/jpg/gif)
│   └── *.md/.txt  ← large clippings, raw dumps
└── resources/     ← non-knowledge artifacts (ignore during normal operations)
    └── attachments/
```

**Ownership rules:**
- `wiki/` — own it entirely. Create, edit, rename, link, merge pages freely.
- `raw/` — read-only. Reference with `source:` key in frontmatter. Never edit.
- `resources/` — ignore during normal operations.
- Root meta files (`CLAUDE.md`, `index.md`, `log.md`) — keep current; update on every operation.

---

## Area organisation

The top level of `wiki/` is a set of thematic **areas** (e.g. Business, Marketing, Psychology). Each area has:
- One `_MOC.md` (Map of Content) — the hub for that area; every page in the area must be linked from it.
- Sub-topic folders for human organisation (CI-invisible — only the first path segment matters for orphan checks).

**`domain:` = the first subdirectory under `wiki/`** regardless of nesting depth.  
A page at `wiki/Psychology/relationships/likeability.md` has `domain: Psychology`.

When bootstrapping, infer areas from the content. Common starting taxonomy: Business, Marketing, Philosophy, Psychology, Communication, Finances, Technology, Life, Reference. Add or remove areas to fit the content.

---

## Page schema

Every `wiki/**/*.md` opens with this YAML frontmatter block:

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
conflicts: true   # optional — only present when a ⚠ Conflicting Views section exists
---
```

### Page types

| Type | Purpose |
|------|---------|
| `source-note` | Distilled notes from one external source (book, article, video, email). |
| `concept` | A framework, idea, or technique that recurs across sources. |
| `entity` | A named person, company, product, or book with its own identity. |
| `moc` | Map of Content — one per area (filename `_MOC.md`). Hub for the area. |
| `synthesis` | Cross-source essay or comparison written from first principles. Original, uncited content is honest as `synthesis`. |
| `topic` | Atomic topic hub aggregating claims across multiple source notes. Cites every claim inline via `[[source]]` wikilinks. Ends with `## Sources in This Wiki` and `## See Also`. Where sources disagree, adds `## ⚠ Conflicting Views` + `conflicts: true`. |

### Status levels

- `raw` — captured but not yet distilled. May be a stub pointing to a `raw/` source.
- `summarized` — clean source notes, one source, not yet cross-linked.
- `synthesized` — cross-referenced, backlinked, connected to the graph.

**Filename convention:** lowercase `kebab-case.md`. Human-readable title lives in `title:`.

**Linking:** Use `[[Page-Slug]]` wikilinks in the page body. Also add to `related:` array. Every page must be linked from its domain `_MOC.md`. Links resolve by basename — path prefix is ignored — so files can move between folders without breaking links.

---

## NO-FABRICATION rule for `topic` pages

Every claim on a `type: topic` page must be attributed to a source note via an inline `[[wikilink]]`. Direct quotes go in quotation marks. Never invent or paraphrase without a citation. If a claim cannot be attributed to an existing source note, either omit it or create a `synthesis` page instead.

---

## Conflict-flagging convention

When a `topic` page contains claims from two or more sources that directly contradict each other:

1. Add `## ⚠ Conflicting Views` before `## Sources in This Wiki`. Present each conflicting position as a bullet attributed to its source:
   ```
   - Position A ([[source-a]])
   - Position B ([[source-b]])
   ```
   No editorial verdict — just the positions.
2. Add `conflicts: true` in frontmatter (after `status:`).

Only flag conflicts traceable to extant source notes. If a claimed conflict is not supported by notes on disk, note the gap in `log.md` instead of fabricating.

---

## Operations

### BOOTSTRAP — creating a new wiki from scratch

1. Create the directory structure: `wiki/`, `raw/`, `resources/attachments/`.
2. Copy the CI scripts from this skill's `assets/ci/` into `.ci/` and make them executable:
   `chmod +x .ci/*.sh .ci/pre-commit`
3. Install the pre-commit hook: `git config core.hooksPath .ci` (or symlink manually).
4. Move all raw source files (large clippings, PDFs, images) into `raw/` or `resources/`.
5. Decide on 4–10 top-level areas. Create each as `wiki/<Area>/` with a skeleton `_MOC.md`.
6. Sort existing notes into the correct area folders. Add YAML frontmatter to each.
7. Create `index.md` (one line per page, grouped by area) and `log.md` with a first entry.
8. Write or update `CLAUDE.md` at the repo root pointing to this skill for future sessions.
9. Run `bash .ci/check-all.sh` and fix all failures before committing.
10. Append to `log.md`: `## [YYYY-MM-DD] bootstrap | Initial wiki setup`.

### INGEST — adding a new source

1. Read the source (from `raw/` or a new file the user provides).
2. Discuss key takeaways with the user if they are present.
3. Create or update the wiki page (`source-note` type; link to raw source in `source:`).
4. Scan the wiki for **entity and concept pages** touched by the source — update them.
5. Add `[[wikilinks]]` from the new page to related existing pages; update `related:` of affected pages.
6. Add the new page to `index.md` (1-line summary, grouped by domain).
7. Link it from its domain `_MOC.md` under the appropriate sub-theme.
8. Run `bash .ci/check-all.sh` and fix any failures.
9. Append to `log.md`: `## [YYYY-MM-DD] ingest | Source Title`.

### QUERY — answering a question

1. Read `index.md` to find candidate pages.
2. Read relevant `_MOC.md` hubs and drill into the pages.
3. Synthesize an answer with `[[wikilinks]]` citations.
4. **If the answer is substantive** (a comparison, analysis, framework, insight) — **file it back as a wiki page** (`synthesis` or `concept` type) so explorations compound.
5. Append to `log.md`: `## [YYYY-MM-DD] query | Question summary`.

### LINT — health-checking the wiki

Run periodically or when asked to keep the wiki healthy:

1. **Contradictions** — pages that disagree on a fact; flag and note which is newer.
2. **Stale claims** — pages superseded by more recent sources; mark with `status: raw` + a note.
3. **Orphans** — pages not linked from any `_MOC.md`.
4. **Missing concept pages** — terms mentioned in 3+ pages that lack their own page.
5. **Absent cross-references** — obvious related pages not linked.
6. **Data gaps** — claims that could be verified or enriched.
7. **Non-atomic topic pages** — `topic` pages covering more than one coherent concept; propose splits.
8. Append to `log.md`: `## [YYYY-MM-DD] lint | Summary of findings`.

---

## CI invariants

Five checks enforced by `bash .ci/check-all.sh` (scripts in `assets/ci/`):

1. **check-frontmatter** — every `wiki/**/*.md` has valid frontmatter with required keys and enum values (`type`, `status`).
2. **check-links** — every `[[wikilink]]` resolves to an existing wiki page (resolved by basename).
3. **check-orphans** — every wiki page is linked from its top-level area's `_MOC.md`.
4. **check-layout** — `wiki/` contains only `.md` files; no `unsorted/` directory.
5. **check-log** — `log.md` has at least one correctly-prefixed entry (`## [YYYY-MM-DD]`).

Run `bash .ci/check-all.sh` before every commit. Install as a pre-commit hook so it runs automatically.

**To bootstrap CI in a new repo:**
```bash
mkdir -p .ci
cp <skill-assets>/ci/* .ci/
chmod +x .ci/*.sh .ci/pre-commit
git config core.hooksPath .ci
```
The CI scripts are in `assets/ci/` bundled with this skill.

---

## `_MOC.md` template

```markdown
---
title: <Area> — Map of Content
type: moc
domain: <Area>
tags: [tag1, tag2]
source: original
date: YYYY-MM-DD
status: synthesized
related: []
---

# <Area>

**N pages** · [[OtherArea/_MOC]] · ...

---

## Sub-topic Name

- [[page-slug]] — one-liner description *(type)*

---

## See Also (other areas)

- [[OtherArea/_MOC]] — cross-domain reference note
```

---

## `index.md` format

```markdown
# Wiki Index

Content catalog — one line per page, grouped by area.

---

## <Area>

### Sub-topic
- [[slug]] — one-liner (type/status)
```

---

## `log.md` format

Append-only. Each entry:
```
## [YYYY-MM-DD] <operation> | <subject>

One-paragraph description of what was done.

---
```

Operations: `bootstrap`, `ingest`, `query`, `lint`, `refactor`, `restructure`.

---

## Atomicity principle

Each `topic` page should cover exactly one coherent concept. If a page grows beyond ~150 lines or contains sections that belong to distinct areas, propose splitting it. Extracted sections become new pages in their correct area. The original page retains the core concept; extracted pages link back via `## See Also`.

---

## Reference files bundled with this skill

- `references/moc-examples.md` — annotated example MOC files for different area types.
- `assets/ci/` — the complete set of CI shell scripts ready to copy into a new repo.
