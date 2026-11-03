# Meta-file templates

Copy-paste skeletons for the three structures a wiki maintains by hand. Read this when
bootstrapping a wiki, adding a new area, or appending a log entry. For the shaping decisions and
"done" criteria that make an area hub good — not a sample to copy — see `moc-examples.md`.

## Bootstrapping a new wiki

New wiki from scratch:

1. Create `wiki/`, `raw/`, `resources/attachments/`.
2. Copy this skill's `assets/ci/` into `.ci/`, then `chmod +x .ci/*.sh .ci/pre-commit` and
   install the hook: `git config core.hooksPath .ci`.
3. Move raw source files (clippings, PDFs, images) into `raw/` or `resources/`.
4. Choose 4–10 areas; create each as `wiki/<Area>/` with a skeleton `_MOC.md`.
5. Sort existing notes into area folders and add frontmatter to each.
6. Write `index.md` (one line per page, grouped by area) and `log.md` (first entry).
7. Write `CLAUDE.md` at the repo root pointing future sessions at this skill.
8. Run `bash .ci/check-all.sh`, fix every failure, then log `bootstrap`.

To wire CI into a fresh repo:

```bash
mkdir -p .ci && cp <skill-assets>/ci/* .ci/
chmod +x .ci/*.sh .ci/pre-commit
git config core.hooksPath .ci
```

## `_MOC.md` (one per area)

Every page in the area must appear in exactly one sub-topic list here — that is what
`check-orphans` verifies. The header page count excludes the MOC itself.

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

- [[page-slug]] — one-liner description _(type)_

---

## See Also (other areas)

- [[OtherArea/_MOC]] — cross-domain reference note
```

Conventions: list entities first when an area has them; use `·` to separate breadcrumbs; make the
sub-section names match the sub-topic folder names so the hub mirrors the folder tree.

## `index.md` (repo root)

The flat catalogue queries read first. One line per page, grouped by area then sub-topic, so an
LLM can pick candidate pages before opening anything.

```markdown
# Wiki Index

Content catalog — one line per page, grouped by area.

---

## <Area>

### Sub-topic

- [[slug]] — one-liner (type/status)
```

## `log.md` (repo root)

Append-only. Each operation adds one entry at the top; never rewrite history — the log is how a
future session reconstructs what happened without the conversation transcript.

```
## [YYYY-MM-DD] <operation> | <subject>

One-paragraph description of what was done.

---
```

Operations: `bootstrap`, `ingest`, `query`, `lint`, `refactor`, `restructure`. `check-log`
requires at least one entry matching the `## [YYYY-MM-DD] op | subject` prefix.
