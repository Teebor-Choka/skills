// Review-engine tests. Run: nix shell nixpkgs#nodejs --command node --test test.mjs
// (imports the deck-io fixture builder + ingest via the leaf's relative path).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildMinimalPptx } from "../../../deck-io/scripts/fixtures/build.mjs";
import { emit } from "../../../deck-io/scripts/emit.mjs";
import { review } from "./review.mjs";
import { REGISTRY } from "./registry.mjs";

const fixture = path.join(os.tmpdir(), `review-${process.pid}.pptx`);
fs.writeFileSync(fixture, buildMinimalPptx());
let r;

test("review the fixture deck", async () => {
  r = await review(fixture);
  assert.equal(r.deck.slideCount, 4);
});

test("deterministic verdicts match the seeded violations", () => {
  const by = Object.fromEntries(r.reproducible.map((c) => [c.id, c]));
  assert.equal(by["ant-fonts"].status, "fail");
  assert.ok(
    by["ant-fonts"].evidence.some((e) => e.fontPt === 12),
    "cites the 12pt run",
  );
  assert.equal(by["bullet-riddled-corpse"].status, "fail");
  assert.ok(by["bullet-riddled-corpse"].evidence.some((e) => e.bullets === 9));
  assert.equal(by["injured-outlines"].status, "fail");
  assert.equal(by["floodmarks"].status, "fail");
  assert.equal(by["fontaholic"].status, "pass");
  assert.equal(by["slideuments"].status, "pass");
  assert.equal(by["backtracking"].status, "info");
  assert.equal(by["bookends"].status, "info"); // fixture has no closing bookend
});

test("headline score is reproducible (2 pass / 6 applicable)", () => {
  assert.equal(r.headline.score, 33);
  assert.equal(r.headline.band, "red");
  assert.equal(r.headline.applicable, 6);
});

test("failing antipatterns with a fixOp surface as available fixes", () => {
  const ops = r.fixes_available.map((f) => f.op);
  assert.ok(ops.includes("raiseFonts"));
  assert.ok(ops.includes("stripMasterLogo"));
  assert.ok(ops.includes("splitOverBulletSlide"));
});

test("safe-fix round-trip: apply fixes → re-ingest → violations clear, score rises", async () => {
  const fixed = path.join(os.tmpdir(), `review-fixed-${process.pid}.pptx`);
  await emit(fixture, [{ op: "raiseFonts" }, { op: "stripMasterLogo" }], fixed);
  const r2 = await review(fixed);
  const by = Object.fromEntries(r2.reproducible.map((c) => [c.id, c]));
  assert.equal(
    by["ant-fonts"].status,
    "pass",
    "Ant Fonts cleared after raiseFonts",
  );
  assert.equal(
    by["floodmarks"].status,
    "pass",
    "Floodmarks cleared after stripMasterLogo",
  );
  assert.ok(r2.headline.score > r.headline.score, "headline improved");
});

test("plan-presence tier is skipped without a sidecar", () => {
  const by = Object.fromEntries(r.reproducible.map((c) => [c.id, c]));
  assert.equal(by["big-why"].status, "skip");
  assert.equal(by["carnegie-hall"].status, "skip");
});

test("plan-presence tier: with a sidecar, present→pass, missing→fail", async () => {
  const r3 = await review(fixture, {
    plan: { big_why: "ship trust", rehearsal_count: 3 },
  });
  const by = Object.fromEntries(r3.reproducible.map((c) => [c.id, c]));
  assert.equal(by["big-why"].status, "pass");
  assert.equal(by["carnegie-hall"].status, "pass"); // rehearsal_count present
  assert.equal(by["know-your-audience"].status, "info"); // absent → advisory, never a fail
  assert.equal(r3.headline.score, 33); // plan-presence never moves the artifact headline
});

test("llm tier is emitted as advisory jobs, never scored", () => {
  assert.equal(r.llm_jobs.length, 19);
  assert.ok(
    r.llm_jobs.every(
      (j) => typeof j.rubric === "string" && j.inputs && j.inputs.slideTexts,
    ),
  );
  const ids = new Set(r.llm_jobs.map((j) => j.id));
  assert.ok(ids.has("narrative-arc") && ids.has("tower-of-babble"));
  assert.ok(
    !r.reproducible.some((c) => c.tier === "llm"),
    "no llm row leaks into the scored set",
  );
});

test("unscoreable live-delivery patterns are listed, not scored", () => {
  assert.equal(r.unscoreable.length, 11);
  const ids = r.unscoreable.map((u) => u.id);
  assert.ok(
    ids.includes("hiccup-words") &&
      ids.includes("live-demo") &&
      ids.includes("echo-chamber"),
  );
});

test("marker + animation patterns reported (advisory, out of headline)", () => {
  const by = Object.fromEntries(r.reproducible.map((c) => [c.id, c]));
  assert.equal(by["breadcrumbs"].status, "pass"); // "Agenda" slide present
  assert.equal(by["coda"].status, "info");
  assert.equal(by["intermezzi"].status, "info");
  assert.equal(by["soft-transitions"].status, "pass"); // consistent fade
  assert.equal(by["preroll"].status, "pass"); // slide 1 auto-advances
  assert.equal(by["gradual-consistency"].status, "pass"); // slide 3 animation
  assert.equal(r.headline.score, 33); // P techniques never move the AP-only headline
});

test("registry integrity: 88 rows, 63 P / 25 AP, files+tiers valid, checks resolve", async () => {
  const det = await import("./checks/deterministic.mjs");
  const files = new Set([
    "01-prelude.md",
    "02-creativity.md",
    "03-slides.md",
    "04-temporal.md",
    "05-demos.md",
    "06-stageprep.md",
    "07-antipatterns.md",
    "08-perf.md",
  ]);
  const tiers = new Set([
    "deterministic",
    "animation",
    "llm",
    "plan-presence",
    "unscoreable",
  ]);
  const ids = new Set();
  let p = 0,
    ap = 0;
  for (const row of REGISTRY) {
    assert.ok(!ids.has(row.id), `duplicate id ${row.id}`);
    ids.add(row.id);
    assert.ok(tiers.has(row.tier), `bad tier ${row.tier} (${row.id})`);
    assert.ok(files.has(row.file), `bad file ${row.file} (${row.id})`);
    assert.ok(["P", "AP"].includes(row.type));
    row.type === "P" ? p++ : ap++;
    if (row.check)
      assert.equal(
        typeof det[row.check],
        "function",
        `check ${row.check} resolves`,
      );
  }
  assert.equal(REGISTRY.length, 88, "88 rows");
  assert.equal(p, 63, "63 patterns");
  assert.equal(ap, 25, "25 antipatterns");
});
