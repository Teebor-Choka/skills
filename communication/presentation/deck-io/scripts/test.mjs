// deck-io ingest tests. Run: nix shell nixpkgs#nodejs --command node --test test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildMinimalPptx } from "./fixtures/build.mjs";
import { ingest } from "./ingest.mjs";
import { validateIR } from "./ir.mjs";

const fixture = path.join(os.tmpdir(), `deckio-${process.pid}.pptx`);
fs.writeFileSync(fixture, buildMinimalPptx());
let deck;

test("ingest minimal.pptx → structurally valid IR", async () => {
  deck = await ingest(fixture);
  assert.deepEqual(validateIR(deck), []);
  assert.equal(deck.source.format, "pptx");
  assert.equal(deck.meta.slideCount, 4);
  assert.equal(deck.meta.title, "My Talk");
  assert.equal(deck.masters.length, 1);
  assert.equal(deck.masters[0].logos.length, 1);
});

test("typography + bullet structure captured (slide 3)", () => {
  const s3 = deck.slides[2];
  assert.ok(
    s3.runs.some((r) => r.fontPt === 12),
    "the 12pt footnote run is present",
  );
  assert.equal(
    s3.paragraphs.filter((p) => p.isBullet && p.level === 0).length,
    9,
  );
  assert.ok(
    s3.paragraphs.some((p) => p.level === 1 && p.isBullet),
    "a lone level-1 sub-bullet is present",
  );
});

test("inherited bullets (no explicit buChar) detected via body placeholder", () => {
  const s2 = deck.slides[1]; // "Agenda": 3 body paragraphs, bullets inherited from layout
  assert.equal(s2.paragraphs.filter((p) => p.isBullet).length, 3);
});

test("duplicate detection, notes, and fonts", () => {
  assert.equal(
    deck.slides[3].isDuplicateOf,
    2,
    "slide 4 duplicates slide 2 (Backtracking)",
  );
  assert.match(deck.slides[0].notes, /Opening remarks/);
  const fonts = [
    ...new Set(deck.slides.flatMap((s) => s.runs.map((r) => r.fontName))),
  ];
  assert.ok(
    fonts.includes("Arial") && fonts.includes("Calibri"),
    "explicit Arial + inherited Calibri",
  );
});

test("inherited fonts + sizes resolved from theme / master txStyles", () => {
  const titleRun = deck.slides[0].runs.find((r) => r.text === "My Talk");
  assert.equal(titleRun.fontName, "Arial", "title → theme majorFont");
  assert.equal(titleRun.fontPt, 44, "title → titleStyle size");
  const bodyRun = deck.slides[1].runs.find((r) => r.text === "First point");
  assert.equal(bodyRun.fontName, "Calibri", "body → theme minorFont");
  assert.equal(bodyRun.fontPt, 28, "body → bodyStyle lvl1 size");
});

test("transitions + animations ingested (Phase 2)", () => {
  assert.equal(deck.slides[0].transition?.type, "fade");
  assert.equal(
    deck.slides[0].transition?.auto,
    true,
    "slide 1 auto-advances (advTm)",
  );
  assert.equal(deck.slides[1].transition?.type, "fade");
  assert.ok(
    deck.slides[2].animations.length >= 1,
    "slide 3 carries a build animation",
  );
});

test("capabilities reflect pptx source", () => {
  assert.equal(deck.source.capabilities.animation, true);
  assert.equal(deck.source.capabilities.fontsPerRun, true);
});
