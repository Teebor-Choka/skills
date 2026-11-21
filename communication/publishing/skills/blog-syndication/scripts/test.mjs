// Test suite for the blog-syndication toolkit. Run: node --test test.mjs
// Zero extra deps — node:test + node:assert.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  parseSource,
  validateAll,
  rewriteBody,
  platformTags,
  canonicalFor,
  targetsFor,
} from "./lib.mjs";
import { loadAdapter } from "./loader.mjs";
import astro from "./adapters/astro.mjs";
import devto from "./adapters/devto.mjs";
import medium from "./adapters/medium.mjs";
import substack from "./adapters/substack.mjs";
import { verifyBuild } from "./verify.mjs";

const CFG = {
  site: {
    labsBaseUrl: "https://example.com/labs",
    assetsBaseUrl: "https://example.com",
    assetsPath: "/labs-assets",
    author: "Author",
  },
  astro: {},
  devto: { maxTags: 4 },
  medium: { maxTags: 5 },
  _dir: os.tmpdir(),
};

const goodData = {
  slug: "my-post",
  title: "My Post",
  subtitle: "A dek",
  excerpt: "Short summary.",
  publishDate: new Date("2026-07-13"),
  draft: true,
  status: "deep-dive",
  tags: ["Nix", "macOS", "NixOS", "DevOps", "MDM"],
  coverImage: "img:cover.png",
  coverImageAlt: "alt",
  series: "Declarative Everything",
};
const goodBody =
  "See [Post 1](post:other-post).\n\n![d](img:diagram.png)\n> **Figure prompt:** strip me\n\nDone.\n";

// ── parseSource ──────────────────────────────────────────────────────────────
test("parseSource splits frontmatter and body", () => {
  const { data, body } = parseSource("---\ntitle: X\n---\nhello\n");
  assert.equal(data.title, "X");
  assert.equal(body.trim(), "hello");
});
test("parseSource throws without frontmatter", () => {
  assert.throws(() => parseSource("no frontmatter here"));
});

// ── validateAll ──────────────────────────────────────────────────────────────
test("validateAll passes a good post", () => {
  const posts = [
    { file: "a.md", data: goodData, body: goodBody },
    { file: "b.md", data: { ...goodData, slug: "other-post" }, body: "x" },
  ];
  const [r] = validateAll(posts, CFG);
  assert.deepEqual(r.errors, []);
});
test("validateAll flags missing required fields", () => {
  const [r] = validateAll(
    [{ file: "a.md", data: { slug: "x" }, body: "" }],
    CFG,
  );
  assert.ok(r.errors.some((e) => e.includes("title")));
  assert.ok(r.errors.some((e) => e.includes("excerpt")));
  assert.ok(r.errors.some((e) => e.includes("publishDate")));
});
test("validateAll flags bad slug, bad status, unknown cross-link", () => {
  const posts = [
    {
      file: "a.md",
      data: { ...goodData, slug: "Bad Slug", status: "nope" },
      body: "[x](post:ghost)",
    },
  ];
  const [r] = validateAll(posts, CFG, { adapters: { astro } });
  assert.ok(r.errors.some((e) => e.includes("kebab-case")));
  assert.ok(r.errors.some((e) => e.includes("status")));
  assert.ok(r.errors.some((e) => e.includes("unknown post slug")));
});
test("validateAll flags duplicate slug and unbalanced block", () => {
  const posts = [
    { file: "a.md", data: goodData, body: "<!-- syndicate:only astro -->\nx" },
    { file: "b.md", data: goodData, body: "y" },
  ];
  const results = validateAll(posts, CFG);
  assert.ok(results[0].errors.some((e) => e.includes("duplicate slug")));
  assert.ok(results[0].errors.some((e) => e.includes("unbalanced")));
});
test("validateAll --strict promotes warnings to errors", () => {
  const longExcerpt = "x".repeat(200);
  const posts = [
    { file: "a.md", data: { ...goodData, excerpt: longExcerpt }, body: "x" },
  ];
  const [loose] = validateAll(posts, CFG);
  const [strict] = validateAll(posts, CFG, { strict: true });
  assert.ok(loose.warnings.length > 0 && loose.errors.length === 0);
  assert.ok(strict.errors.length > 0);
});

// ── rewriteBody ──────────────────────────────────────────────────────────────
test("rewriteBody: astro cross-link is root-relative, image under assetsPath", () => {
  const out = rewriteBody(goodBody, {
    platform: "astro",
    absolute: false,
    slug: "my-post",
    config: CFG,
  });
  assert.match(out, /\]\(\/labs\/other-post\)/);
  assert.match(out, /\]\(\/labs-assets\/my-post\/diagram\.png\)/);
});
test("rewriteBody: external cross-link + image are absolute", () => {
  const out = rewriteBody(goodBody, {
    platform: "medium",
    absolute: true,
    slug: "my-post",
    config: CFG,
  });
  assert.match(out, /\]\(https:\/\/example\.com\/labs\/other-post\)/);
  assert.match(
    out,
    /\]\(https:\/\/example\.com\/labs-assets\/my-post\/diagram\.png\)/,
  );
});
test("rewriteBody: figure prompt is stripped", () => {
  const out = rewriteBody(goodBody, {
    platform: "astro",
    absolute: false,
    slug: "my-post",
    config: CFG,
  });
  assert.doesNotMatch(out, /Figure prompt/);
});
test("rewriteBody: only/except blocks respected per platform", () => {
  const body = [
    "<!-- syndicate:only astro -->",
    "ASTRO_ONLY",
    "<!-- syndicate:end -->",
    "<!-- syndicate:except medium -->",
    "NOT_MEDIUM",
    "<!-- syndicate:end -->",
    "ALWAYS",
  ].join("\n");
  const astroOut = rewriteBody(body, {
    platform: "astro",
    absolute: false,
    slug: "s",
    config: CFG,
  });
  const mediumOut = rewriteBody(body, {
    platform: "medium",
    absolute: true,
    slug: "s",
    config: CFG,
  });
  assert.match(astroOut, /ASTRO_ONLY/);
  assert.match(astroOut, /NOT_MEDIUM/);
  assert.doesNotMatch(mediumOut, /ASTRO_ONLY/);
  assert.doesNotMatch(mediumOut, /NOT_MEDIUM/);
  assert.match(mediumOut, /ALWAYS/);
});

// ── platformTags ─────────────────────────────────────────────────────────────
test("platformTags: devto normalizes + truncates to 4", () => {
  const tags = platformTags(goodData, "devto", CFG);
  assert.equal(tags.length, 4);
  assert.ok(tags.every((t) => /^[a-z0-9]+$/.test(t)));
});
test("platformTags: medium truncates to 5, preserves case", () => {
  const tags = platformTags(goodData, "medium", CFG);
  assert.equal(tags.length, 5);
  assert.ok(tags.includes("macOS"));
});
test("platformTags: per-platform override wins", () => {
  const d = { ...goodData, devto: { tags: ["only", "these"] } };
  assert.deepEqual(platformTags(d, "devto", CFG), ["only", "these"]);
});

// ── emitters ─────────────────────────────────────────────────────────────────
test("toAstro: Date preserved, canonical set, tokens resolved", () => {
  const out = astro.emit(goodData, goodBody, CFG);
  const { data } = parseSource(out);
  assert.ok(data.publishDate instanceof Date);
  assert.equal(data.metadata.canonical, "https://example.com/labs/my-post");
  assert.equal(data.image, "/labs-assets/my-post/cover.png");
  assert.doesNotMatch(out, /\]\(post:|\]\(img:/);
});
test("toDevto: tags string, canonical_url, published boolean", () => {
  const out = devto.emit({ ...goodData, draft: false }, goodBody, CFG);
  const { data } = parseSource(out);
  assert.equal(typeof data.tags, "string");
  assert.equal(data.tags.split(",").length, 4);
  assert.equal(data.published, true);
  assert.equal(data.canonical_url, "https://example.com/labs/my-post");
});
test("toMedium: starts with H1, no frontmatter, absolute urls", () => {
  const out = medium.emit(goodData, goodBody, CFG);
  assert.ok(out.startsWith("# My Post"));
  assert.doesNotMatch(out, /^---/);
  assert.match(out, /https:\/\/example\.com\/labs\/other-post/);
});
test("canonicalFor honors override", () => {
  assert.equal(
    canonicalFor({ ...goodData, canonicalUrl: "https://x.dev/p" }, CFG),
    "https://x.dev/p",
  );
});
test("targetsFor defaults to all platforms", () => {
  assert.deepEqual(targetsFor({}), ["astro", "devto", "medium", "substack"]);
});

// ── verifyBuild (generated-document validation) ──────────────────────────────
test("verifyBuild passes on real emitter output", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "bs-vb-"));
  const data = { ...goodData, slug: "my-post" };
  const other = { ...goodData, slug: "other-post" };
  for (const [pl, ad] of [
    ["astro", astro],
    ["devto", devto],
    ["medium", medium],
    ["substack", substack],
  ]) {
    fs.mkdirSync(path.join(dir, pl), { recursive: true });
    fs.writeFileSync(
      path.join(dir, pl, "my-post.md"),
      ad.emit(data, goodBody, CFG),
    );
    fs.writeFileSync(
      path.join(dir, pl, "other-post.md"),
      ad.emit(other, "body\n", CFG),
    );
    if (typeof ad.sidecar === "function") {
      for (const s of ["my-post", "other-post"])
        fs.writeFileSync(
          path.join(dir, pl, `${s}.meta.json`),
          JSON.stringify({
            title: "T",
            canonicalUrl: `https://example.com/labs/${s}`,
          }),
        );
    }
  }
  const { ok, results } = await verifyBuild(dir, CFG);
  assert.ok(
    ok,
    JSON.stringify(
      results.filter((r) => r.errors.length),
      null,
      2,
    ),
  );
});

test("verifyBuild catches leaked token, wrong date, missing sidecar, relative external link", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "labs-vb-bad-"));
  // astro with a leaked token + quoted (string) publishDate
  fs.mkdirSync(path.join(dir, "astro"), { recursive: true });
  fs.writeFileSync(
    path.join(dir, "astro", "x.md"),
    '---\ntitle: X\npublishDate: "2026-07-13"\nmetadata:\n  canonical: https://example.com/labs/x\n---\nsee [a](post:ghost)\n',
  );
  // medium with root-relative link and no sidecar
  fs.mkdirSync(path.join(dir, "medium"), { recursive: true });
  fs.writeFileSync(
    path.join(dir, "medium", "x.md"),
    "# Title\n\n[a](/labs/other)\n",
  );
  const { ok, results } = await verifyBuild(dir, CFG);
  assert.equal(ok, false);
  const astro = results.find((r) => r.platform === "astro");
  const medium = results.find((r) => r.platform === "medium");
  assert.ok(astro.errors.some((e) => e.includes("post:")));
  assert.ok(astro.errors.some((e) => e.includes("publishDate")));
  assert.ok(medium.errors.some((e) => e.includes("root-relative")));
  assert.ok(medium.errors.some((e) => e.includes("sidecar")));
});

// ── lazy adapters / core isolation ────────────────────────────────────────────
test("emitters live in adapters, not core; adapters load lazily by id", async () => {
  const core = await import("./lib.mjs");
  assert.equal(
    core.toAstro,
    undefined,
    "toAstro must not be exported from core",
  );
  assert.equal(core.toDevto, undefined);
  assert.equal(core.toMedium, undefined);
  const a = await loadAdapter("devto");
  assert.equal(a.id, "devto");
  assert.equal(typeof a.emit, "function");
  assert.equal(typeof a.validate, "function");
  await assert.rejects(() => loadAdapter("nope"), /unknown platform/);
});

test("astro sourceValidate owns the status enum; core alone does not", () => {
  const bad = [
    { file: "a.md", data: { ...goodData, status: "nope" }, body: "x" },
  ];
  const [withAstro] = validateAll(bad, CFG, { adapters: { astro } });
  const [without] = validateAll(bad, CFG);
  assert.ok(withAstro.errors.some((e) => e.includes("status")));
  assert.ok(!without.errors.some((e) => e.includes("status")));
});
