# Neutral Post Source Standard (v1)

One post = one Markdown file with YAML frontmatter, written **once** in a
platform-agnostic form. The toolkit generates the per-platform variants
(your Astro site, dev.to, Medium, Substack) from this single source. This is
the [POSSE](https://indieweb.org/POSSE) model: **P**ublish on your **O**wn
**S**ite, **S**yndicate **E**verywhere — the neutral source is the master, your
own site holds the canonical URL, and every syndicated copy points back to it.

---

## 1. File & directory layout

```
<content-root>/
  syndicate.config.json      # site + platform config (see §6)
  posts/
    01-declarative-macos.md  # neutral source (order prefix optional, ignored for slug)
    07-nix-darwin-vs-mdm.md
  assets/
    <slug>/                  # per-post images, referenced as img:<file>
      cover.png
      layered-stack.png
  build/                     # generated — never edited by hand (git-ignored)
    astro/<slug>.md
    devto/<slug>.md
    medium/<slug>.md   + <slug>.meta.json
    substack/<slug>.md + <slug>.meta.json
    report.json
```

The **order prefix** (`07-`) is a human sort aid only. The URL comes from the
`slug` field, never the filename.

---

## 2. Frontmatter schema

Required: `slug`, `title`, `excerpt`, `publishDate`.

```yaml
---
# ── Identity ───────────────────────────────────────────────
slug: nix-darwin-vs-mdm # URL slug. Canonical = <labsBaseUrl>/<slug>
title: "nix-darwin vs MDM: One Flake to Provision a Mac, a VM, and a NixOS Box"
subtitle: "Where each wins, where nix-darwin can't follow" # optional — Substack subtitle / dek

# One tight sentence or two. Reused as: the astro `excerpt`, HTML meta description,
# dev.to `description`. Keep ≤ 160 chars for clean SEO (warning above that).
excerpt: >
  A head-to-head between nix-darwin and macOS MDM — where each wins, where
  nix-darwin can't follow, and why one flake also builds a NixOS box and a VM.

# ── Lifecycle ──────────────────────────────────────────────
publishDate: 2026-07-13 # date (YYYY-MM-DD) or ISO datetime
updateDate: # optional
draft: true # default true. `false` = eligible to publish
status: deep-dive # astro-adapter maturity: idea | prototype | deep-dive

# ── Taxonomy ───────────────────────────────────────────────
author: Your Name # default from config.site.author
category: Infrastructure # optional single category (astro taxonomy)
tags: [nix, nix-darwin, macos, nixos, mdm, devops] # canonical tag list
series: "Declarative Everything" # optional. dev.to series; on-site grouping

# ── Media ──────────────────────────────────────────────────
coverImage: img:cover.png # optional. img:<file> resolves under assets/<slug>/
coverImageAlt: "Two-layer stack: MDM authority over nix-darwin reproducibility"

# ── Syndication ────────────────────────────────────────────
canonicalUrl: # optional override; else derived from slug
platforms: [astro, devto, medium, substack] # default: all four
devto: { tags: [nix, macos, nixos, devops] } # optional per-platform tag override (≤4)
medium: { tags: [Nix, macOS, NixOS, DevOps, MDM] } # optional (≤5)
---
```

### Field → platform mapping

| Neutral field  | Astro                              | dev.to                | Medium               | Substack          |
| -------------- | ---------------------------------- | --------------------- | -------------------- | ----------------- |
| `title`        | `title`                            | `title`               | H1 (first line)      | title (meta)      |
| `subtitle`     | —                                  | —                     | —                    | subtitle (meta)   |
| `excerpt`      | `excerpt` + `metadata.description` | `description`         | —                    | —                 |
| `slug`         | filename → `/labs/<slug>`          | —                     | —                    | —                 |
| `publishDate`  | `publishDate`                      | — (API `published`)   | —                    | —                 |
| `draft`        | `draft`                            | `published: !draft`   | —                    | —                 |
| `status`       | `status`                           | —                     | —                    | —                 |
| `author`       | `author`                           | —                     | —                    | —                 |
| `category`     | `category`                         | —                     | —                    | —                 |
| `tags`         | `tags`                             | `tags` (≤4, lc-alnum) | tags (≤5)            | tags (meta)       |
| `series`       | — (grouping)                       | `series`              | —                    | —                 |
| `coverImage`   | `image`                            | `cover_image`         | inline top image     | inline top image  |
| `canonicalUrl` | `metadata.canonical`               | `canonical_url`       | manual (Import tool) | manual (settings) |

Fields with no target cell are carried only where meaningful; Medium/Substack
have no frontmatter, so their metadata is written to a `<slug>.meta.json`
sidecar for you to paste into the editor.

---

## 3. Body conventions (CommonMark)

Write normal Markdown. Three project-specific tokens make the body portable:

### 3.1 Cross-post links — `post:<slug>`

Link to another post in the series by **slug**, never by file path or URL:

```markdown
The factory is covered in [Post 1](post:declarative-macos).
```

The converter rewrites this per target:

- **Astro** → root-relative `/labs/declarative-macos`
- **dev.to / Medium / Substack** → absolute `https://example.com/labs/declarative-macos`
  (so off-site readers always land on your canonical copy)

An unknown slug is a **validation error** (catches typos and renames).

### 3.2 Images — `img:<file>`

Reference images by filename; the file must exist under `assets/<slug>/`:

```markdown
![Layered stack diagram](img:layered-stack.png)
```

Rewritten to:

- **Astro** → `/labs-assets/<slug>/layered-stack.png` (served from `public/`)
- **external** → `https://example.com/labs-assets/<slug>/layered-stack.png`

External platforms cannot resolve relative paths, so image URLs are always made
absolute for them. A missing asset is a **warning** for drafts, an **error**
under `--strict` / when `draft: false`.

### 3.3 Figure prompts are stripped

A blockquote whose first line begins with `**Figure prompt:**` is a production
note (a prompt for generating the diagram). It is **removed from every output**:

```markdown
![Stack](img:stack.png)

> **Figure prompt:** Flat vector diagram, dark charcoal background… ← stripped
```

### 3.4 Platform include/exclude blocks

Fence content that belongs to some platforms only:

```markdown
<!-- syndicate:only astro -->

## Series index

| # | Post | … |

<!-- syndicate:end -->

<!-- syndicate:except medium substack -->

…detail that is noise off-site…

<!-- syndicate:end -->
```

`only <list>` keeps the block **only** for the listed platforms; `except <list>`
keeps it for all **but** the listed ones. Blocks must be closed with
`<!-- syndicate:end -->` (unbalanced fences are a validation error).

---

## 4. Validation rules

`validate.mjs` enforces, per post:

**Errors** (block publish, nonzero exit):

- Missing required field (`slug`, `title`, `excerpt`, `publishDate`).
- `slug` not `^[a-z0-9]+(-[a-z0-9]+)*$`.
- `status` not one of `idea|prototype|deep-dive`.
- `publishDate` / `updateDate` not a valid date.
- `tags` not an array of strings.
- `post:<slug>` link to an unknown post.
- Unbalanced `syndicate:` block.
- Duplicate slug across the post set.

**Warnings** (surfaced, don't block drafts):

- `excerpt` > 160 chars (SEO snippet truncation).
- `title` > 70 chars.
- `> 4` dev.to tags or `> 5` Medium tags after mapping.
- dev.to tag not lowercase-alphanumeric.
- `coverImage` / `img:` asset file missing.
- `draft: false` but `publishDate` in the future (or vice-versa).

`--strict` promotes all warnings to errors. `convert.mjs` refuses to emit a
platform output for a post with errors targeting that platform.

### 4.1 Generated-document validation (`verify.mjs`)

Source validation is not enough — the _output_ must also be well-formed.
`convert.mjs` runs `verify.mjs` automatically after writing `build/`, and it can
be run standalone (`node verify.mjs build`). It checks every generated file:

- **All platforms:** no leaked `post:`/`img:` token, no `**Figure prompt:**`
  note, no unprocessed `<!-- syndicate: -->` directive, non-empty body.
- **astro:** mirrors the astro adapter's `post` zod schema — `title` string,
  `publishDate` a real **Date** (not a quoted string — `z.date()` rejects
  strings), `status` enum, `tags` string[], `metadata.canonical` an absolute
  URL, `image` root-relative under the assets path, cross-links root-relative
  (`/labs/…`, not absolute).
- **dev.to:** `title`, boolean `published`, absolute `canonical_url`, absolute
  `cover_image`, `tags` ≤ max and lowercase-alphanumeric.
- **Medium / Substack:** no frontmatter, starts with an `# H1`, links absolute
  (no root-relative), and a parseable `<slug>.meta.json` with title + absolute
  `canonicalUrl`.

A nonzero exit here fails the workflow. The toolkit ships a test suite
(`node --test test.mjs`, 21 cases) covering the library and this verifier.

---

## 5. Publishing model per platform

| Platform     | How the toolkit delivers                                                                                                  | Canonical set by                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| **Astro**    | Copy `build/astro/<slug>.md` into your content collection; commit; deploy                                                 | `metadata.canonical` in frontmatter (self) |
| **dev.to**   | hand `build/devto/<slug>.md` to the external n8n workflow (Forem API), or paste it                                        | `canonical_url` frontmatter                |
| **Medium**   | Paste `build/medium/<slug>.md`, **or** use Medium's _Import a story_ on the live `/labs/<slug>` URL (auto-sets canonical) | Import tool, or Story settings → canonical |
| **Substack** | Paste `build/substack/<slug>.md`; set title/subtitle from the `.meta.json` sidecar                                        | Post settings → canonical URL              |

Medium retired new integration tokens and Substack has no write API, so those
two are export-and-paste by design. Always publish to **your own site first**,
let it be the canonical URL, then syndicate.

---

## 6. Config (`syndicate.config.json`)

```json
{
  "site": {
    "labsBaseUrl": "https://example.com/labs",
    "assetsBaseUrl": "https://example.com",
    "assetsPath": "/labs-assets",
    "author": "Your Name"
  },
  "astro": { "labsDir": "../your-site/src/data/blog" },
  "devto": { "maxTags": 4 },
  "medium": { "maxTags": 5 }
}
```

Resolved relative to the config file's directory. Scripts look for
`syndicate.config.json` in the current directory (or `--config <path>`), falling
back to the skill's bundled defaults.
</content>
