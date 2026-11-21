#!/usr/bin/env node
// Post-generation validation: check the GENERATED documents in build/ (not the
// neutral source). Runs automatically at the end of convert.mjs, and standalone:
//   node verify.mjs [build-dir] [--config path]
// Each platform's rules live in its adapter's validate(); adapters load lazily,
// so only the platforms present in build/ are imported. Exit 1 if any doc fails.
import fs from "node:fs";
import path from "node:path";
import { loadConfig } from "./lib.mjs";
import { loadAdapter, PLATFORMS } from "./loader.mjs";

// Checks that apply to every generated document, regardless of platform.
function commonChecks(raw, errors) {
  if (/\]\(post:/.test(raw))
    errors.push('unresolved cross-link token "](post:" left in output');
  if (/\]\(img:/.test(raw))
    errors.push('unresolved image token "](img:" left in output');
  if (/\*\*Figure prompt:\*\*/i.test(raw))
    errors.push("figure-prompt note leaked into output");
  if (/<!--\s*syndicate:/.test(raw))
    errors.push("unprocessed syndicate directive left in output");
  if (!raw.trim()) errors.push("empty document");
}

// Programmatic entry — convert.mjs calls this. Returns {ok, results}. Async
// because adapters are imported lazily per present platform.
export async function verifyBuild(outDir, config) {
  const results = [];
  for (const platform of PLATFORMS) {
    const dir = path.join(outDir, platform);
    if (!fs.existsSync(dir)) continue;
    const adapter = await loadAdapter(platform);
    for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".md"))) {
      const slug = f.replace(/\.md$/, "");
      const raw = fs.readFileSync(path.join(dir, f), "utf8");
      const errors = [];
      commonChecks(raw, errors);
      try {
        errors.push(...(adapter.validate(raw, { slug, dir, config }) || []));
      } catch (e) {
        errors.push(`${platform}: check threw — ${e.message}`);
      }
      results.push({ platform, slug, file: path.join(platform, f), errors });
    }
  }
  return { ok: results.every((r) => r.errors.length === 0), results };
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const argv = process.argv.slice(2);
  const ci = argv.indexOf("--config");
  const config = loadConfig(ci >= 0 ? argv[ci + 1] : undefined);
  const outDir =
    argv.find((a, i) => !a.startsWith("--") && argv[i - 1] !== "--config") ||
    "build";
  const { ok, results } = await verifyBuild(outDir, config);
  let errs = 0;
  for (const r of results) {
    if (r.errors.length) {
      console.log(`✗ ${r.file}`);
      for (const e of r.errors) {
        console.log(`  ERROR  ${e}`);
        errs++;
      }
    } else {
      console.log(`✓ ${r.file}`);
    }
  }
  console.log(
    `\n${ok ? "✓" : "✗"} verified ${results.length} generated doc(s), ${errs} error(s)`,
  );
  process.exit(ok ? 0 : 1);
}
