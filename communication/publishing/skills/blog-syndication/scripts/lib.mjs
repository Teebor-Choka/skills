// blog-syndication core library.
// Neutral post source -> generic validation + shared conversion helpers.
// Platform-specific emit/validate live in ./adapters/<id>.mjs and load lazily
// (see ./loader.mjs). Single dependency: js-yaml (frontmatter parsing).
import fs from "node:fs";
import path from "node:path";
import yaml from "js-yaml";

// Known platform adapters (ids only — the modules load lazily via loader.mjs).
export const PLATFORMS = ["astro", "devto", "medium", "substack"];
const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

// ── Config ───────────────────────────────────────────────────────────────────
// Generic defaults; real values belong in syndicate.config.json at the content
// root. Per-adapter blocks (e.g. devto.maxTags) are conventional fallbacks that a
// config or an adapter may override.
const DEFAULT_CONFIG = {
  site: {
    labsBaseUrl: "https://example.com/blog",
    assetsBaseUrl: "https://example.com",
    assetsPath: "/blog-assets",
    author: "Author",
  },
  astro: { labsDir: null },
  devto: { maxTags: 4 },
  medium: { maxTags: 5 },
};

export function loadConfig(explicitPath, cwd = process.cwd()) {
  const found = explicitPath || findUp("syndicate.config.json", cwd);
  if (!found) return { ...DEFAULT_CONFIG, _dir: cwd };
  const raw = JSON.parse(fs.readFileSync(found, "utf8"));
  const merged = {
    ...raw,
    site: { ...DEFAULT_CONFIG.site, ...(raw.site || {}) },
    astro: { ...DEFAULT_CONFIG.astro, ...(raw.astro || {}) },
    devto: { ...DEFAULT_CONFIG.devto, ...(raw.devto || {}) },
    medium: { ...DEFAULT_CONFIG.medium, ...(raw.medium || {}) },
    _dir: path.dirname(found),
  };
  return merged;
}

function findUp(name, from) {
  let dir = path.resolve(from);
  for (;;) {
    const p = path.join(dir, name);
    if (fs.existsSync(p)) return p;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

// ── Parsing ──────────────────────────────────────────────────────────────────
export function parseSource(raw, file = "<string>") {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!m) throw new Error(`${file}: no YAML frontmatter block found`);
  let data;
  try {
    data = yaml.load(m[1]) || {};
  } catch (e) {
    throw new Error(`${file}: frontmatter is not valid YAML — ${e.message}`);
  }
  if (typeof data !== "object" || Array.isArray(data))
    throw new Error(`${file}: frontmatter must be a mapping`);
  return { data, body: m[2] };
}

export function readPost(file) {
  const { data, body } = parseSource(fs.readFileSync(file, "utf8"), file);
  return { file, data, body };
}

// Split an optional frontmatter block; returns {data, body, hadFrontmatter}.
// Used by adapter generated-document validators.
export function splitFrontmatter(raw) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(raw);
  if (!m) return { data: null, body: raw, hadFrontmatter: false };
  return { data: yaml.load(m[1]) || {}, body: m[2], hadFrontmatter: true };
}

// ── Helpers ──────────────────────────────────────────────────────────────────
export const isDate = (v) => v instanceof Date && !isNaN(v.valueOf());
export const asDate = (v) =>
  isDate(v)
    ? v
    : typeof v === "string" && !isNaN(Date.parse(v))
      ? new Date(v)
      : null;
export const isAbsUrl = (v) => typeof v === "string" && /^https?:\/\//.test(v);

export function canonicalFor(data, config) {
  if (data.canonicalUrl) return data.canonicalUrl;
  return `${config.site.labsBaseUrl.replace(/\/$/, "")}/${data.slug}`;
}

export function assetUrl(file, slug, config, { absolute }) {
  const base = `${config.site.assetsPath.replace(/\/$/, "")}/${slug}/${file}`;
  return absolute
    ? `${config.site.assetsBaseUrl.replace(/\/$/, "")}${base}`
    : base;
}

export function slugifyTag(t) {
  return String(t)
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

// Tags the given platform will actually publish (after override + truncation).
export function platformTags(data, platform, config) {
  const src = (data[platform] && data[platform].tags) || data.tags || [];
  if (platform === "devto")
    return src
      .map(slugifyTag)
      .filter(Boolean)
      .slice(0, (config.devto && config.devto.maxTags) ?? 4);
  if (platform === "medium")
    return src.slice(0, (config.medium && config.medium.maxTags) ?? 5);
  return src;
}

// ── Validation (generic source rules; adapters add their own via sourceValidate)─
// posts: [{file,data,body}]. adapters: {id: adapterModule} already loaded by the
// caller. For each post, the sourceValidate() of every targeted adapter runs.
// Returns [{file, slug, errors:[], warnings:[]}].
export function validateAll(
  posts,
  config,
  { strict = false, adapters = {} } = {},
) {
  const slugs = new Map();
  for (const p of posts)
    if (p.data.slug) slugs.set(p.data.slug, (slugs.get(p.data.slug) || 0) + 1);
  const known = new Set(slugs.keys());

  return posts.map((p) => {
    const errors = [];
    const warnings = [];
    const d = p.data;

    // Required fields
    for (const f of ["slug", "title", "excerpt", "publishDate"])
      if (d[f] === undefined || d[f] === null || d[f] === "")
        errors.push(`missing required field: ${f}`);

    if (d.slug && !SLUG_RE.test(d.slug))
      errors.push(`slug "${d.slug}" is not kebab-case [a-z0-9-]`);
    if (d.slug && slugs.get(d.slug) > 1)
      errors.push(`duplicate slug "${d.slug}" across post set`);
    if (d.publishDate !== undefined && !asDate(d.publishDate))
      errors.push(`publishDate is not a valid date`);
    if (
      d.updateDate !== undefined &&
      d.updateDate !== null &&
      !asDate(d.updateDate)
    )
      errors.push(`updateDate is not a valid date`);
    if (
      d.tags !== undefined &&
      (!Array.isArray(d.tags) || d.tags.some((t) => typeof t !== "string"))
    )
      errors.push(`tags must be an array of strings`);
    if (d.platforms !== undefined) {
      if (!Array.isArray(d.platforms))
        errors.push(`platforms must be an array`);
      else
        for (const pl of d.platforms)
          if (!PLATFORMS.includes(pl)) errors.push(`unknown platform "${pl}"`);
    }

    // Body checks
    const links = [...p.body.matchAll(/\]\(post:([^)\s]+)\)/g)].map(
      (m) => m[1],
    );
    for (const s of links)
      if (!known.has(s)) errors.push(`cross-link to unknown post slug "${s}"`);

    const blockErr = checkBlocks(p.body);
    if (blockErr) errors.push(blockErr);

    // Warnings
    if (typeof d.excerpt === "string" && d.excerpt.trim().length > 160)
      warnings.push(
        `excerpt is ${d.excerpt.trim().length} chars (>160 may truncate in search results)`,
      );
    if (typeof d.title === "string" && d.title.length > 70)
      warnings.push(`title is ${d.title.length} chars (>70)`);

    // Per-platform tag sanity (conventional; adapters may add stricter rules)
    const rawDevto = (d.devto && d.devto.tags) || d.tags || [];
    const devtoMax = (config.devto && config.devto.maxTags) ?? 4;
    if (rawDevto.length > devtoMax)
      warnings.push(
        `dev.to allows ≤${devtoMax} tags; ${rawDevto.length} given (will truncate)`,
      );
    for (const t of rawDevto)
      if (slugifyTag(t) !== String(t).toLowerCase())
        warnings.push(
          `dev.to tag "${t}" will be normalized to "${slugifyTag(t)}"`,
        );
    const rawMedium = (d.medium && d.medium.tags) || d.tags || [];
    const mediumMax = (config.medium && config.medium.maxTags) ?? 5;
    if (rawMedium.length > mediumMax)
      warnings.push(
        `Medium allows ≤${mediumMax} tags; ${rawMedium.length} given (will truncate)`,
      );

    // Asset existence
    for (const f of referencedAssets(d, p.body)) {
      const abs = path.join(config._dir || ".", "assets", d.slug || "", f);
      if (!fs.existsSync(abs))
        warnings.push(`asset not found: assets/${d.slug}/${f}`);
    }

    // Draft/date coherence
    const pub = asDate(d.publishDate);
    if (d.draft === false && pub && pub.valueOf() > Date.now())
      warnings.push(`draft:false but publishDate is in the future`);

    // Adapter-specific source rules (lazy: only targeted adapters, only if loaded)
    for (const id of targetsFor(d)) {
      const a = adapters[id];
      if (a && typeof a.sourceValidate === "function") {
        const r = a.sourceValidate(d, config) || {};
        for (const e of r.errors || []) errors.push(e);
        for (const w of r.warnings || []) warnings.push(w);
      }
    }

    const finalErrors = strict ? [...errors, ...warnings] : errors;
    return {
      file: p.file,
      slug: d.slug,
      errors: finalErrors,
      warnings: strict ? [] : warnings,
    };
  });
}

function referencedAssets(data, body) {
  const out = new Set();
  if (typeof data.coverImage === "string" && data.coverImage.startsWith("img:"))
    out.add(data.coverImage.slice(4));
  for (const m of body.matchAll(/\]\(img:([^)\s]+)\)/g)) out.add(m[1]);
  return [...out];
}

function checkBlocks(body) {
  let depth = 0;
  for (const line of body.split("\n")) {
    if (/<!--\s*syndicate:(only|except)\s+[^>]*-->/.test(line)) depth++;
    else if (/<!--\s*syndicate:end\s*-->/.test(line)) {
      depth--;
      if (depth < 0)
        return "unbalanced syndicate block: unexpected syndicate:end";
    }
  }
  if (depth !== 0)
    return `unbalanced syndicate block: ${depth} unclosed block(s)`;
  return null;
}

// ── Body rewriting ───────────────────────────────────────────────────────────
// opts: { platform, absolute, slug, config }. `platform` selects syndicate:
// only/except blocks; `absolute` picks absolute vs. root-relative link/image URLs
// (the canonical own-site adapter passes absolute:false, external adapters true).
export function rewriteBody(body, { platform, absolute, slug, config }) {
  let out = applyBlocks(body, platform);
  out = stripFigurePrompts(out);
  // Cross-post links
  out = out.replace(/\]\(post:([^)\s]+)\)/g, (_, s) => {
    const url = absolute
      ? `${config.site.labsBaseUrl.replace(/\/$/, "")}/${s}`
      : `/${trimBase(config.site.labsBaseUrl)}/${s}`.replace(/\/+/g, "/");
    return `](${url})`;
  });
  // Images
  out = out.replace(
    /\]\(img:([^)\s]+)\)/g,
    (_, f) => `](${assetUrl(f, slug, config, { absolute })})`,
  );
  return out.replace(/\n{3,}/g, "\n\n").trim() + "\n";
}

function trimBase(url) {
  try {
    return new URL(url).pathname.replace(/^\/|\/$/g, "");
  } catch {
    return url.replace(/^\//, "").replace(/\/$/, "");
  }
}

function stripFigurePrompts(body) {
  const lines = body.split("\n");
  const out = [];
  let inPrompt = false;
  for (const line of lines) {
    if (inPrompt) {
      if (/^\s*>/.test(line)) continue; // still inside the blockquote
      inPrompt = false;
    }
    if (/^\s*>\s*\*\*Figure prompt:\*\*/i.test(line)) {
      inPrompt = true;
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

function applyBlocks(body, platform) {
  const lines = body.split("\n");
  const out = [];
  const stack = []; // {keep:boolean}
  const open = /<!--\s*syndicate:(only|except)\s+([^>]*?)\s*-->/;
  for (const line of lines) {
    const mo = open.exec(line);
    if (mo) {
      const list = mo[2].split(/[\s,]+/).filter(Boolean);
      const inList = list.includes(platform);
      const keep = mo[1] === "only" ? inList : !inList;
      stack.push({ keep: keep && stack.every((s) => s.keep) });
      continue;
    }
    if (/<!--\s*syndicate:end\s*-->/.test(line)) {
      stack.pop();
      continue;
    }
    if (stack.every((s) => s.keep)) out.push(line);
  }
  return out.join("\n");
}

// ── Frontmatter emitter helper (used by adapters) ─────────────────────────────
// Drop null/undefined recursively while PRESERVING Date instances (a JSON
// round-trip would stringify Dates, and z.date() in the Astro schema rejects
// strings). js-yaml then dumps Date values as unquoted ISO timestamps.
function prune(v) {
  if (v === undefined || v === null) return undefined;
  if (v instanceof Date) return v;
  if (Array.isArray(v)) return v.map(prune).filter((x) => x !== undefined);
  if (typeof v === "object") {
    const o = {};
    for (const [k, val] of Object.entries(v)) {
      const pv = prune(val);
      if (pv !== undefined) o[k] = pv;
    }
    return o;
  }
  return v;
}

export function yamlFront(obj) {
  const clean = prune(obj) || {};
  return `---\n${yaml.dump(clean, { lineWidth: 100, quotingType: '"', forceQuotes: false }).trimEnd()}\n---\n`;
}

export function targetsFor(data) {
  return Array.isArray(data.platforms) ? data.platforms : PLATFORMS;
}
