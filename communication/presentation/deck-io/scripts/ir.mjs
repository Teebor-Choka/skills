// Neutral deck IR — the check-derived union of everything the 88 pattern checks
// read. deck-io adapters populate this. It is intentionally review-agnostic: the
// `plan` field is left null here and attached later by patterns/review.mjs, so
// deck-io never learns about review concepts (keeps the leaf clean).

// Per-format capability truth table. A check consults these to self-suppress
// (status:'skipped') instead of producing a false pass when its inputs are not
// observable from the given source.
export const CAPABILITIES = {
  pptx: {
    fontsPerRun: true,
    animation: true,
    transitions: true,
    speakerNotes: true,
    master: true,
    embeddedVideo: true,
    hyperlinks: true,
    theme: true,
  },
  // pdf preset (Phase 4) — degraded; declared now so checks reason uniformly.
  pdf: {
    fontsPerRun: "partial",
    animation: false,
    transitions: false,
    speakerNotes: false,
    master: false,
    embeddedVideo: false,
    hyperlinks: true,
    theme: false,
  },
};

export function makeDeck(format, path) {
  return {
    source: { format, path, capabilities: { ...(CAPABILITIES[format] || {}) } },
    meta: {
      slideCount: 0,
      slideWidthEmu: null,
      slideHeightEmu: null,
      theme: { name: null, isStockDefault: null },
      title: null,
    },
    masters: [],
    slides: [],
    plan: null, // attached by review.mjs, never by deck-io
  };
}

export function makeSlide(index) {
  return {
    index,
    layout: null,
    title: null,
    runs: [], // { text, fontName, fontPt, bold, italic, color, shapeId }
    paragraphs: [], // { level, isBullet, bulletChar, text, shapeId }
    images: [], // { embedId, bbox, isPhoto, isClipart, origin }
    shapes: [], // { id, type, bbox, isLogo }
    wordCount: 0,
    blankAreaPct: null,
    notes: null,
    hyperlinks: [], // { text, href }
    isDuplicateOf: null,
    markerRole: null, // 'bookend' | 'intermezzo' | 'breadcrumb' | 'coda' | null
    transition: null, // pptx only (Phase 2)
    animations: [], // pptx only (Phase 2)
  };
}

// Structural sanity check on a populated IR (not a schema for the source file).
export function validateIR(deck) {
  const errs = [];
  if (!deck || typeof deck !== "object") return ["deck is not an object"];
  if (!deck.source || !deck.source.format) errs.push("source.format missing");
  if (!Array.isArray(deck.slides)) return [...errs, "slides is not an array"];
  if (deck.meta.slideCount !== deck.slides.length)
    errs.push(
      `meta.slideCount ${deck.meta.slideCount} != slides.length ${deck.slides.length}`,
    );
  deck.slides.forEach((s, i) => {
    if (s.index !== i + 1)
      errs.push(`slide ${i}: index ${s.index} != ${i + 1}`);
    for (const r of s.runs)
      if (r.fontPt !== null && typeof r.fontPt !== "number")
        errs.push(`slide ${s.index}: run fontPt must be number|null`);
    for (const p of s.paragraphs)
      if (typeof p.level !== "number")
        errs.push(`slide ${s.index}: paragraph.level must be number`);
  });
  return errs;
}
