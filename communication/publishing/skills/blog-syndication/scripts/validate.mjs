#!/usr/bin/env node
// Validate neutral post sources. Usage:
//   node validate.mjs [posts-dir-or-files...] [--config path] [--strict]
// Exit code 0 = all clean; 1 = at least one error.
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

const argv = process.argv.slice(2);
const strict = argv.includes("--strict");
const cfgI = argv.indexOf("--config");
const configPath = cfgI >= 0 ? argv[cfgI + 1] : undefined;
const inputs = argv.filter(
  (a, i) => !a.startsWith("--") && !(i > 0 && argv[i - 1] === "--config"),
);

const files = collectFiles(inputs.length ? inputs : ["posts"]);
if (!files.length) {
  console.error("no .md source files found in:", inputs.join(", ") || "posts");
  process.exit(1);
}

const config = loadConfig(configPath);
const posts = [];
const parseErrors = [];
for (const f of files) {
  try {
    posts.push(readPost(f));
  } catch (e) {
    parseErrors.push({ file: f, msg: e.message });
  }
}

const wanted = [...new Set(posts.flatMap((p) => targetsFor(p.data)))].filter(
  (pl) => PLATFORMS.includes(pl),
);
const adapters = await loadAdapters(wanted);
const results = validateAll(posts, config, { strict, adapters });
let errorCount = 0;
let warnCount = 0;

for (const pe of parseErrors) {
  errorCount++;
  console.log(`\n✗ ${rel(pe.file)}`);
  console.log(`  ERROR  ${pe.msg}`);
}

for (const r of results) {
  const ok = r.errors.length === 0;
  const mark = ok ? (r.warnings.length ? "⚠" : "✓") : "✗";
  console.log(`\n${mark} ${rel(r.file)}  ${r.slug ? `(${r.slug})` : ""}`);
  for (const e of r.errors) {
    console.log(`  ERROR  ${e}`);
    errorCount++;
  }
  for (const w of r.warnings) {
    console.log(`  warn   ${w}`);
    warnCount++;
  }
}

console.log(
  `\n${errorCount === 0 ? "✓" : "✗"} ${posts.length + parseErrors.length} post(s): ${errorCount} error(s), ${warnCount} warning(s)${strict ? " [strict]" : ""}`,
);
process.exit(errorCount ? 1 : 0);

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
