---
name: blog-syndication
description: >
  Cross-post one blog post to your Astro site, dev.to, Medium and Substack from a single
  source; lint frontmatter and cross-links. Use for "cross-post", "syndicate", "publish on
  Medium and dev.to".
---

# blog-syndication

Publish once, syndicate everywhere (POSSE). A post is written **once** as a
neutral Markdown source; the toolkit validates it and generates per-platform
variants, keeping your own site as the canonical URL.

Full format spec: **[reference/STANDARD.md](reference/STANDARD.md)** — read it
before authoring or editing a source file.

## The pipeline

```
posts/<slug>.md  ──validate──►  ──convert──►  build/{astro,devto,medium,substack}/
   (neutral)                                        │
                                                     ├─ astro/    → copy into your site, deploy (canonical)
                                                     ├─ devto/    → hand off to n8n (frontmatter incl. canonical_url)
                                                     ├─ medium/   → paste + set canonical (or Import tool)
                                                     └─ substack/ → paste + set canonical (meta.json sidecar)
```

This skill **generates** per-platform files; it does not publish them. Actual
publishing is external — e.g. an n8n workflow that watches `build/devto/` and
POSTs to the Forem API, or manual paste for Medium/Substack.

## Architecture — a generic core + lazy platform adapters

- **`scripts/lib.mjs`** — generic core: config, parsing, source validation, body
  rewriting, shared helpers. Knows _nothing_ platform-specific.
- **`scripts/adapters/<id>.mjs`** — one module per platform, each exposing a fixed
  interface `{ id, emit(data, body, config), validate(raw, ctx), sourceValidate?,
sidecar? }`. **Loaded lazily** via `scripts/loader.mjs` — a `--platforms devto`
  run never imports the astro adapter (or its schema).
- **`adapters/astro.mjs` is the one site-specific option.** It carries a concrete
  Astro content-collection schema (a `status` enum, `metadata.canonical`, etc.).
  To target a different site, **fork this one file**; the core and the other
  adapters are untouched.

## When to use

- Writing a new post intended for the site **and** external platforms.
- Standardizing existing posts into a single portable format.
- Linting frontmatter, cross-links, tags, and images before publishing.
- Generating dev.to / Medium / Substack copies with correct canonical URLs.

## Workflow

1. **Author** a neutral source in `posts/<order>-<slug>.md` per the STANDARD.
   Put images in `assets/<slug>/`. Cross-link other posts with `post:<slug>`,
   images with `img:<file>`.
2. **Validate** — never convert or publish before this is clean:
   ```bash
   node scripts/validate.mjs posts            # all drafts
   node scripts/validate.mjs posts --strict   # publish gate (warnings = errors)
   ```
3. **Convert** (auto-verifies the generated output):
   ```bash
   node scripts/convert.mjs posts --out build
   # or a subset: --platforms astro,devto   (loads only those adapters)
   ```
   Converter refuses any post with source validation errors, then runs
   **post-generation validation** on everything it wrote (see below). A green
   convert means every emitted file is well-formed for its platform. To re-check
   an existing `build/` without regenerating:
   ```bash
   node scripts/verify.mjs build
   ```
4. **Publish** (external to this skill):
   - **Your site (astro)**: copy `build/astro/<slug>.md` into your site's content
     collection, copy `assets/<slug>/*` into its public assets dir, run the site's
     build check, commit, deploy. This is the canonical copy — publish it first.
   - **dev.to**: handled by an n8n workflow that consumes `build/devto/<slug>.md`
     (its frontmatter already carries `canonical_url`, `tags`, `cover_image`,
     `series` and `published: <!draft>`).
   - **Medium / Substack**: paste `build/<platform>/<slug>.md`; use the
     `<slug>.meta.json` sidecar for title/subtitle and to set the canonical URL.

## Running (nix/direnv projects)

`node` may live only in a project devshell — or use a bare one:

```bash
cd <content-root>
nix shell nixpkgs#nodejs --command node <skill>/scripts/validate.mjs posts
# or a project devshell that provides node:
direnv exec <path-to-site-repo> node <skill>/scripts/validate.mjs posts
```

## Two layers of validation

1. **Source validation** (`validate.mjs`) — the neutral `posts/*.md` before
   conversion: schema, cross-links, tags, images, balanced blocks. Each targeted
   adapter's `sourceValidate()` adds its own source rules (e.g. the astro adapter
   enforces its `status` enum).
2. **Generated-document validation** (`verify.mjs`) — the `build/**/*.md` after
   conversion. Runs automatically at the end of `convert.mjs`. Each platform's
   rules live in its adapter's `validate()` (loaded lazily): the astro adapter
   mirrors its Astro `post` schema (title, `publishDate` as a real Date, status
   enum, tags, canonical); dev.to/Medium/Substack enforce tag limits, absolute
   URLs, H1 title, sidecar presence. Common checks fail on any leaked
   `post:`/`img:` token, figure-prompt note, or unprocessed `syndicate:` directive.

> The astro-schema replica in `adapters/astro.mjs` lets the pipeline validate
> without the site's toolchain installed. The ultimate gate is still the site's
> own build check after copying `build/astro/*` into the content collection.

## Setup

- Scripts need `js-yaml` (declared in `scripts/package.json`; `node_modules/` is
  gitignored). Once: `cd scripts && npm install` (or `pnpm install`).
- Create `syndicate.config.json` in your content root (see
  `scripts/syndicate.config.example.json`) with the site's base URLs and the
  Astro `labsDir`.
- Run the test suite after editing any script: `npm test` (or
  `node --test test.mjs`). 23 tests cover parsing, source validation, body
  rewriting, tag mapping, the adapters (emit + validate), lazy loading, and
  generated-document verification.

## Rules of thumb

- **Canonical first**: publish to your own site before syndicating; every
  external copy's canonical URL points back to your site's `/<slug>`.
- **Errors block, warnings inform**: a draft may carry warnings; use `--strict`
  as the publish gate.
- **Never hand-edit `build/`** — it is regenerated. Edit the neutral source.
- **New platform?** Add `adapters/<id>.mjs` and its id to `PLATFORMS` in `lib.mjs`.
  Nothing else changes.
