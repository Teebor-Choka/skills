// Deterministic checks — pure functions over the neutral deck IR. Each returns
// { status: 'pass'|'fail'|'skip'|'na'|'info', severity?, evidence: [...], reason? }.
// A check self-suppresses to 'skip' when its inputs aren't observable from the
// source (via deck.source.capabilities), never a false pass.
const MIN_BODY_PT = 20; // Ant Fonts: readable-from-the-back threshold
const MAX_BULLETS = 6; // Bullet-Riddled Corpse: bullets per slide
const MAX_FONTS = 3; // Fontaholic: distinct typefaces per deck
const MAX_WORDS = 40; // Slideuments: words per slide

export function antFonts(deck) {
  if (deck.source.capabilities.fontsPerRun !== true)
    return {
      status: "skip",
      reason: "font sizes not reliably observable from this source",
      evidence: [],
    };
  const bad = [];
  for (const s of deck.slides)
    for (const r of s.runs)
      if (r.fontPt != null && r.fontPt < MIN_BODY_PT && r.text.trim())
        bad.push({
          slide: s.index,
          fontPt: r.fontPt,
          text: r.text.slice(0, 40),
        });
  return bad.length
    ? { status: "fail", severity: "high", evidence: bad }
    : { status: "pass", evidence: [] };
}

export function bulletRiddled(deck) {
  const bad = [];
  for (const s of deck.slides) {
    const n = s.paragraphs.filter((p) => p.isBullet && p.level === 0).length;
    if (n > MAX_BULLETS) bad.push({ slide: s.index, bullets: n });
  }
  return bad.length
    ? { status: "fail", severity: "high", evidence: bad }
    : { status: "pass", evidence: [] };
}

export function injuredOutlines(deck) {
  const bad = [];
  for (const s of deck.slides) {
    const ps = s.paragraphs;
    for (let i = 0; i < ps.length; i++) {
      if (ps[i].level !== 0) continue;
      let kids = 0,
        j = i + 1;
      while (j < ps.length && ps[j].level > 0) {
        if (ps[j].level === 1) kids++;
        j++;
      }
      if (kids === 1)
        bad.push({ slide: s.index, heading: ps[i].text.slice(0, 30) });
      i = j - 1;
    }
  }
  return bad.length
    ? { status: "fail", severity: "medium", evidence: bad }
    : { status: "pass", evidence: [] };
}

export function floodmarks(deck) {
  if (deck.source.capabilities.master !== true)
    return {
      status: "skip",
      reason: "slide master not observable from this source",
      evidence: [],
    };
  const logos = deck.masters.reduce((n, m) => n + m.logos.length, 0);
  return logos > 0
    ? {
        status: "fail",
        severity: "medium",
        evidence: [{ masterLogos: logos, note: "appears on every slide" }],
      }
    : { status: "pass", evidence: [] };
}

export function fontaholic(deck) {
  if (deck.source.capabilities.fontsPerRun !== true)
    return {
      status: "skip",
      reason: "fonts not reliably observable",
      evidence: [],
    };
  const fonts = [
    ...new Set(
      deck.slides.flatMap((s) => s.runs.map((r) => r.fontName)).filter(Boolean),
    ),
  ];
  return fonts.length > MAX_FONTS
    ? { status: "fail", severity: "low", evidence: [{ fonts }] }
    : { status: "pass", evidence: [{ fonts }] };
}

export function slideuments(deck) {
  const bad = [];
  for (const s of deck.slides)
    if (s.wordCount > MAX_WORDS)
      bad.push({ slide: s.index, words: s.wordCount });
  return bad.length
    ? { status: "fail", severity: "medium", evidence: bad }
    : { status: "pass", evidence: [] };
}

// Backtracking is a (P): using it is fine, absence isn't a failure — report as info.
export function backtracking(deck) {
  const dups = deck.slides
    .filter((s) => s.isDuplicateOf)
    .map((s) => ({ slide: s.index, dupOf: s.isDuplicateOf }));
  return dups.length
    ? {
        status: "info",
        note: "duplicate/backtracking slides present",
        evidence: dups,
      }
    : { status: "na", evidence: [] };
}

// Bookends (P): a distinct opening AND closing wrapper slide. Present → pass;
// absent → advisory info (a missing optional pattern must not tank the headline).
const CLOSING_RE =
  /\b(questions|thank you|thanks|contact|q ?& ?a|get in touch|reach me)\b/i;
export function bookends(deck) {
  const first = deck.slides[0];
  const last = deck.slides[deck.slides.length - 1];
  const closingText = last
    ? `${last.title || ""} ${last.paragraphs.map((p) => p.text).join(" ")}`
    : "";
  const hasOpening =
    !!first && (first.markerRole === "bookend" || !!first.title);
  const hasClosing = CLOSING_RE.test(closingText);
  return hasOpening && hasClosing
    ? {
        status: "pass",
        evidence: [{ opening: first.index, closing: last.index }],
      }
    : {
        status: "info",
        note: 'no distinct closing bookend (e.g. a "Questions?"/contact slide)',
        evidence: [],
      };
}

// ── Marker patterns (P, advisory: present→pass, absent→info) ──────────────────
const AGENDA_RE =
  /\b(agenda|outline|overview|contents|roadmap|table of contents)\b/i;
const CODA_RE =
  /\b(appendix|references|resources|backup|further reading|bibliography|coda|links)\b/i;
function bodyWordCount(s) {
  return s.paragraphs
    .filter((p) => p.text && p.text !== s.title)
    .reduce(
      (n, p) => n + (p.text.trim() ? p.text.trim().split(/\s+/).length : 0),
      0,
    );
}

export function breadcrumbs(deck) {
  const hits = deck.slides
    .filter((s) => AGENDA_RE.test(s.title || ""))
    .map((s) => ({ slide: s.index, title: s.title }));
  return hits.length
    ? { status: "pass", evidence: hits }
    : {
        status: "info",
        note: "no agenda/overview slide (Breadcrumbs)",
        evidence: [],
      };
}

export function coda(deck) {
  const start = Math.ceil((deck.slides.length * 2) / 3);
  const hits = deck.slides
    .filter((s, i) => i + 1 > start && CODA_RE.test(s.title || ""))
    .map((s) => ({ slide: s.index, title: s.title }));
  return hits.length
    ? { status: "pass", evidence: hits }
    : {
        status: "info",
        note: "no appendix/references (Coda) slide near the end",
        evidence: [],
      };
}

export function intermezzi(deck) {
  const n = deck.slides.length;
  const dividers = deck.slides
    .filter((s, i) => i > 0 && i < n - 1 && s.title && bodyWordCount(s) <= 3)
    .map((s) => ({ slide: s.index, title: s.title }));
  return dividers.length
    ? { status: "pass", evidence: dividers }
    : {
        status: "info",
        note: "no section-divider (Intermezzi) slides",
        evidence: [],
      };
}

// ── Animation patterns (P, advisory; run only when capabilities.animation) ────
export function softTransitions(deck) {
  const withT = deck.slides.filter((s) => s.transition);
  if (!withT.length)
    return { status: "info", note: "no slide transitions used", evidence: [] };
  const types = [...new Set(withT.map((s) => s.transition.type))];
  return types.length === 1
    ? { status: "pass", evidence: [{ type: types[0], slides: withT.length }] }
    : {
        status: "info",
        note: `mixed transition types (${types.join(", ")}); Soft Transitions favors consistency`,
        evidence: withT.map((s) => ({
          slide: s.index,
          type: s.transition.type,
        })),
      };
}

export function preroll(deck) {
  const first = deck.slides[0];
  return first && first.transition && first.transition.auto
    ? {
        status: "pass",
        evidence: [
          { slide: 1, advanceAfterMs: first.transition.advanceAfterMs },
        ],
      }
    : {
        status: "info",
        note: "no auto-advancing opening slide (Preroll)",
        evidence: [],
      };
}

export function gradualConsistency(deck) {
  const anim = deck.slides
    .filter((s) => s.animations && s.animations.length)
    .map((s) => ({ slide: s.index, animations: s.animations.length }));
  return anim.length
    ? { status: "pass", evidence: anim }
    : {
        status: "info",
        note: "no build/reveal animations (Gradual Consistency)",
        evidence: [],
      };
}
