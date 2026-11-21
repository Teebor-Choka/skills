#!/usr/bin/env node
// Convert neutral post sources into per-platform outputs.
// Usage:
//   node convert.mjs [posts-dir-or-files...] [--config path] [--out build]
//                    [--platforms astro,devto,medium,substack] [--strict]
// Only the targeted platform adapters are imported (lazy). Refuses to emit a
// platform output for a post that has validation errors.
import fs from "node:fs";
import path from "node:path";
import {
  loadConfig,
  readPost,
  validateAll,
  targetsFor,
  PLATFORMS,
} from "./lib.mjs";
import { loadAdapters } from "./loader.mjs";
import { verifyBuild } from "./verify.mjs";

const argv = process.argv.slice(2);
const opt = (name, def) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : def;
};
const strict = argv.includes("--strict");
const outDir = opt("--out", "build");
const only = (opt("--platforms", "") || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const configPath = opt("--config");
const flags = new Set(["--config", "--out", "--platforms"]);
const inputs = argv.filter(
  (a, i) => !a.startsWith("--") && !flags.has(argv[i - 1]),
);

const files = collectFiles(inputs.length ? inputs : ["posts"]);
const config = loadConfig(configPath);
const posts = files.map(readPost);

// Platforms we will touch: explicit --platforms, else the union of each post's
// targets. Intersect with known adapters, then load ONLY those (lazily).
const requested = only.length
  ? only
  : [...new Set(posts.flatMap((p) => targetsFor(p.data)))];
const wanted = requested.filter((pl) => PLATFORMS.includes(pl));
const adapters = await loadAdapters(wanted);

const results = validateAll(posts, config, { strict, adapters });
const byFile = new Map(results.map((r) => [r.file, r]));

const summary = [];
for (const p of posts) {
  const v = byFile.get(p.file);
  if (v.errors.length) {
    console.log(
      `✗ skip ${p.data.slug || rel(p.file)} — ${v.errors.length} error(s) (run validate.mjs)`,
    );
    summary.push({ slug: p.data.slug, skipped: true, errors: v.errors });
    continue;
  }
  const targets = (only.length ? only : targetsFor(p.data)).filter((pl) =>
    PLATFORMS.includes(pl),
  );
  const emitted = [];
  for (const pl of targets) {
    const adapter = adapters[pl];
    const dir = path.join(outDir, pl);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, `${p.data.slug}.md`),
      adapter.emit(p.data, p.body, config),
    );
    emitted.push(pl);
    if (typeof adapter.sidecar === "function") {
      const sc = adapter.sidecar(p.data, config);
      if (sc)
        fs.writeFileSync(
          path.join(dir, `${p.data.slug}.meta.json`),
          JSON.stringify(sc, null, 2) + "\n",
        );
    }
  }
  console.log(`✓ ${p.data.slug} → ${emitted.join(", ")}`);
  summary.push({ slug: p.data.slug, emitted, warnings: v.warnings });
}

console.log(
  `\nWrote ${summary.filter((s) => !s.skipped).length} post(s) to ${outDir}/`,
);

// ── Post-generation validation: verify the GENERATED docs, not just the source.
// This is the workflow's final gate — a green convert means every emitted file
// is well-formed for its platform.
console.log(`\n── verifying generated output ──`);
const { ok: verifyOk, results: verifyResults } = await verifyBuild(
  outDir,
  config,
);
let verifyErrors = 0;
for (const r of verifyResults.filter((r) => r.errors.length)) {
  console.log(`✗ ${r.file}`);
  for (const e of r.errors) {
    console.log(`  ERROR  ${e}`);
    verifyErrors++;
  }
}
console.log(
  `${verifyOk ? "✓" : "✗"} ${verifyResults.length} generated doc(s) verified, ${verifyErrors} error(s)`,
);

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(
  path.join(outDir, "report.json"),
  JSON.stringify(
    {
      generated: "convert.mjs",
      posts: summary,
      verify: { ok: verifyOk, results: verifyResults },
    },
    null,
    2,
  ) + "\n",
);
process.exit(summary.some((s) => s.skipped) || !verifyOk ? 1 : 0);

function collectFiles(inputs) {
  const out = [];
  for (const inp of inputs) {
    if (!fs.existsSync(inp)) continue;
    const st = fs.statSync(inp);
    if (st.isDirectory())
      out.push(
        ...fs
          .readdirSync(inp)
          .filter((f) => f.endsWith(".md"))
          .map((f) => path.join(inp, f)),
      );
    else if (inp.endsWith(".md")) out.push(inp);
  }
  return out.sort();
}
function rel(f) {
  return path.relative(process.cwd(), f) || f;
}
