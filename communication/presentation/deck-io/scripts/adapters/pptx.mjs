// pptx ingest adapter — parses OOXML parts into the neutral deck IR.
// Reads: presentation.xml (slide order + size + master), each slide's spTree
// (text runs w/ font size+name, paragraphs w/ bullet level, pictures, shapes),
// speaker notes, and the master's logos. Animations/transitions are Phase 2.
import fs from "node:fs";
import AdmZip from "adm-zip";
import { XMLParser } from "fast-xml-parser";
import { makeDeck, makeSlide } from "../ir.mjs";

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  textNodeName: "#text",
  trimValues: true,
});
const toArr = (x) => (x == null ? [] : Array.isArray(x) ? x : [x]);
const int = (x, d = 0) => (x == null ? d : parseInt(x, 10));

function textOf(t) {
  if (t == null) return "";
  if (typeof t === "string") return t;
  if (Array.isArray(t)) return t.map(textOf).join("");
  return t["#text"] != null ? String(t["#text"]) : "";
}

function resolvePath(dir, target) {
  if (target.startsWith("/")) return target.slice(1);
  const segs = (dir ? dir.split("/") : []).concat(target.split("/"));
  const out = [];
  for (const s of segs) {
    if (s === "." || s === "") continue;
    if (s === "..") out.pop();
    else out.push(s);
  }
  return out.join("/");
}

function readRels(parts, partPath) {
  const slash = partPath.lastIndexOf("/");
  const dir = slash >= 0 ? partPath.slice(0, slash) : "";
  const base = slash >= 0 ? partPath.slice(slash + 1) : partPath;
  const relsPath = (dir ? dir + "/" : "") + "_rels/" + base + ".rels";
  const map = {};
  if (!parts[relsPath]) return map;
  const xml = parser.parse(parts[relsPath]);
  for (const r of toArr(xml.Relationships?.Relationship))
    map[r["@_Id"]] = {
      type: r["@_Type"],
      target: resolvePath(dir, r["@_Target"]),
    };
  return map;
}

function bboxOf(spPr) {
  const x = spPr?.["a:xfrm"];
  if (!x) return null;
  return {
    x: int(x["a:off"]?.["@_x"]),
    y: int(x["a:off"]?.["@_y"]),
    cx: int(x["a:ext"]?.["@_cx"]),
    cy: int(x["a:ext"]?.["@_cy"]),
  };
}

// Coarse animation-effect collector: walk a <p:timing> tree counting effect nodes.
// Deliberately conservative — `<p:timing>` is deeply nested and tool-divergent, so
// we only surface "which/how-many effects", never fine timing semantics.
const ANIM_RE =
  /(^|:)(anim|animEffect|animClr|animMotion|animRot|animScale|set)$/;
function collectAnimations(node, out = []) {
  if (node == null || typeof node !== "object") return out;
  for (const [k, v] of Object.entries(node)) {
    if (ANIM_RE.test(k))
      for (const _ of toArr(v)) out.push({ effect: k.split(":").pop() });
    for (const child of toArr(v)) collectAnimations(child, out);
  }
  return out;
}

function parseTextShape(sp, slide, shapeId, ctx) {
  const txBody = sp["p:txBody"];
  const ph = sp["p:nvSpPr"]?.["p:nvPr"]?.["p:ph"];
  const phType = ph?.["@_type"] ?? null;
  const phIdx = ph?.["@_idx"];
  const isTitle = phType === "title" || phType === "ctrTitle";
  // A body/content placeholder bullets its paragraphs BY DEFAULT — the list
  // formatting is inherited from the layout/master, so real slide XML carries no
  // a:buChar. Treat body/obj placeholders (incl. type-less idx placeholders) as
  // bulleted unless a paragraph explicitly opts out with a:buNone.
  const isBodyPlaceholder =
    !!ph &&
    !isTitle &&
    phType !== "subTitle" &&
    (phType === "body" ||
      phType === "obj" ||
      (phType === null && phIdx !== undefined));
  for (const p of toArr(txBody?.["a:p"])) {
    const pPr = p["a:pPr"] || {};
    const level = int(pPr["@_lvl"], 0);
    let paraText = "";
    for (const r of toArr(p["a:r"])) {
      const rPr = r["a:rPr"] || {};
      const sz = rPr["@_sz"];
      const t = textOf(r["a:t"]);
      paraText += t;
      // Explicit run formatting wins; otherwise resolve from the master/theme
      // (title runs → majorFont/titleStyle; body runs → minorFont/bodyStyle[level]).
      let fontName = rPr["a:latin"]?.["@_typeface"] ?? null;
      let fontPt = sz != null ? int(sz) / 100 : null;
      if (ctx) {
        if (fontName == null)
          fontName = isTitle ? ctx.fonts.major : ctx.fonts.minor;
        if (fontPt == null)
          fontPt = isTitle
            ? ctx.styles.title
            : (ctx.styles.body[level + 1] ??
              ctx.styles.body[1] ??
              ctx.styles.other);
      }
      slide.runs.push({
        text: t,
        fontName,
        fontPt,
        bold: rPr["@_b"] === "1",
        italic: rPr["@_i"] === "1",
        color: null,
        shapeId,
      });
    }
    const explicitBullet = "a:buChar" in pPr || "a:buAutoNum" in pPr;
    const isBullet =
      !("a:buNone" in pPr) &&
      (explicitBullet || (isBodyPlaceholder && paraText.trim().length > 0));
    const bulletChar = pPr["a:buChar"]?.["@_char"] ?? null;
    slide.paragraphs.push({
      level,
      isBullet,
      bulletChar,
      text: paraText,
      shapeId,
    });
    if (isTitle && !slide.title && paraText) slide.title = paraText;
  }
  return phType;
}

function parseSlide(parts, slidePath, index, ctx) {
  const slide = makeSlide(index);
  const xml = parser.parse(parts[slidePath]);
  const tree = xml["p:sld"]?.["p:cSld"]?.["p:spTree"];
  const rels = readRels(parts, slidePath);

  for (const sp of toArr(tree?.["p:sp"])) {
    const id = int(sp["p:nvSpPr"]?.["p:cNvPr"]?.["@_id"]);
    const phType = parseTextShape(sp, slide, id, ctx);
    slide.shapes.push({
      id,
      type: phType || "body",
      bbox: bboxOf(sp["p:spPr"]),
      isLogo: false,
    });
  }
  for (const pic of toArr(tree?.["p:pic"])) {
    const id = int(pic["p:nvPicPr"]?.["p:cNvPr"]?.["@_id"]);
    const embed = pic["p:blipFill"]?.["a:blip"]?.["@_r:embed"] ?? null;
    const bbox = bboxOf(pic["p:spPr"]);
    slide.images.push({
      embedId: embed,
      src: rels[embed]?.target ?? null,
      bbox,
      isPhoto: null,
      isClipart: null,
      origin: "embedded",
    });
    slide.shapes.push({ id, type: "pic", bbox, isLogo: false });
  }

  // transitions + animations (Phase 2)
  const sld = xml["p:sld"] || {};
  const tr = sld["p:transition"];
  if (tr) {
    const typeKey = Object.keys(tr).find((k) => !k.startsWith("@_"));
    slide.transition = {
      type: typeKey ? typeKey.split(":").pop() : "unknown",
      auto: tr["@_advTm"] != null,
      advanceAfterMs: tr["@_advTm"] != null ? int(tr["@_advTm"]) : null,
      spd: tr["@_spd"] ?? null,
    };
  }
  if (sld["p:timing"]) {
    try {
      slide.animations = collectAnimations(sld["p:timing"]);
    } catch {
      slide.animations = [];
    }
  }

  // speaker notes
  const notesRel = Object.values(rels).find((r) =>
    r.type.endsWith("/notesSlide"),
  );
  if (notesRel && parts[notesRel.target]) {
    const nx = parser.parse(parts[notesRel.target]);
    const ntree = nx["p:notes"]?.["p:cSld"]?.["p:spTree"];
    let txt = "";
    for (const sp of toArr(ntree?.["p:sp"]))
      for (const p of toArr(sp["p:txBody"]?.["a:p"]))
        for (const r of toArr(p["a:r"])) txt += textOf(r["a:t"]) + " ";
    slide.notes = txt.trim() || null;
  }

  slide.wordCount = slide.runs.reduce(
    (n, r) => n + (r.text.trim() ? r.text.trim().split(/\s+/).length : 0),
    0,
  );
  slide.markerRole = index === 1 ? "bookend" : null;
  return slide;
}

function parseMaster(parts, masterPath) {
  if (!parts[masterPath]) return null;
  const xml = parser.parse(parts[masterPath]);
  const tree = xml["p:sldMaster"]?.["p:cSld"]?.["p:spTree"];
  const rels = readRels(parts, masterPath);
  const logos = [];
  for (const pic of toArr(tree?.["p:pic"])) {
    const embed = pic["p:blipFill"]?.["a:blip"]?.["@_r:embed"] ?? null;
    logos.push({
      src: rels[embed]?.target ?? null,
      bbox: bboxOf(pic["p:spPr"]),
    });
  }
  return { id: masterPath, logos, placeholders: [] };
}

// Theme font scheme (majorFont = headings, minorFont = body) — the inherited
// typefaces for runs without an explicit a:latin.
function parseThemeFonts(parts, masterPath) {
  const rels = readRels(parts, masterPath);
  const themeRel = Object.values(rels).find((r) => r.type.endsWith("/theme"));
  if (!themeRel || !parts[themeRel.target]) return { major: null, minor: null };
  const fs = parser.parse(parts[themeRel.target])["a:theme"]?.[
    "a:themeElements"
  ]?.["a:fontScheme"];
  return {
    major: fs?.["a:majorFont"]?.["a:latin"]?.["@_typeface"] ?? null,
    minor: fs?.["a:minorFont"]?.["a:latin"]?.["@_typeface"] ?? null,
  };
}

// Master text-style default sizes (titleStyle / bodyStyle[level] / otherStyle) —
// the inherited font size for runs without an explicit sz.
function parseTxStyles(parts, masterPath) {
  const ts = parts[masterPath]
    ? parser.parse(parts[masterPath])["p:sldMaster"]?.["p:txStyles"]
    : null;
  const szOf = (style, lvl) => {
    const sz = style?.[`a:lvl${lvl}pPr`]?.["a:defRPr"]?.["@_sz"];
    return sz != null ? int(sz) / 100 : null;
  };
  const body = {};
  for (let l = 1; l <= 9; l++) {
    const s = szOf(ts?.["p:bodyStyle"], l);
    if (s != null) body[l] = s;
  }
  return {
    title: szOf(ts?.["p:titleStyle"], 1),
    body,
    other: szOf(ts?.["p:otherStyle"], 1),
  };
}

function signature(slide) {
  return slide.paragraphs
    .map((p) => p.text.trim())
    .filter(Boolean)
    .join("|");
}

function ingest(file) {
  const zip = new AdmZip(fs.readFileSync(file));
  const parts = {};
  for (const e of zip.getEntries())
    if (!e.isDirectory) parts[e.entryName] = e.getData().toString("utf8");

  const deck = makeDeck("pptx", file);
  const rootRels = readRels(parts, ""); // reads _rels/.rels
  const office = Object.values(rootRels).find((r) =>
    r.type.endsWith("/officeDocument"),
  );
  const presPath = office?.target || "ppt/presentation.xml";
  const pres = parser.parse(parts[presPath])["p:presentation"];
  const presRels = readRels(parts, presPath);

  const sz = pres["p:sldSz"];
  deck.meta.slideWidthEmu = int(sz?.["@_cx"], 9144000);
  deck.meta.slideHeightEmu = int(sz?.["@_cy"], 6858000);
  const slideArea = deck.meta.slideWidthEmu * deck.meta.slideHeightEmu;

  // master
  const masterId = pres["p:sldMasterIdLst"]?.["p:sldMasterId"]?.["@_r:id"];
  const masterPath = presRels[masterId]?.target;
  let ctx = null;
  if (masterPath) {
    const m = parseMaster(parts, masterPath);
    if (m) deck.masters.push(m);
    ctx = {
      fonts: parseThemeFonts(parts, masterPath),
      styles: parseTxStyles(parts, masterPath),
    };
  }

  // slides in sldIdLst order
  const seen = [];
  for (const sldId of toArr(pres["p:sldIdLst"]?.["p:sldId"])) {
    const rid = sldId["@_r:id"];
    const spath = presRels[rid]?.target;
    if (!spath || !parts[spath]) continue;
    const slide = parseSlide(parts, spath, deck.slides.length + 1, ctx);
    const covered = slide.shapes.reduce(
      (a, s) => a + (s.bbox ? s.bbox.cx * s.bbox.cy : 0),
      0,
    );
    slide.blankAreaPct = slideArea
      ? Math.max(0, Math.min(1, 1 - covered / slideArea))
      : null;
    const sig = signature(slide);
    const dupIdx = seen.findIndex((s) => s === sig && s);
    slide.isDuplicateOf = dupIdx >= 0 ? dupIdx + 1 : null;
    seen.push(sig);
    deck.slides.push(slide);
  }
  deck.meta.slideCount = deck.slides.length;
  deck.meta.title = deck.slides[0]?.title ?? null;
  return deck;
}

// Safe-fix: in-place OOXML mutation (never regenerate — untouched bytes stay
// intact). Operates on the raw part XML, not a re-serialized parse tree.
// Supported ops: raiseFonts (bump sub-threshold run sizes), stripMasterLogo
// (remove logo pictures from masters). splitOverBulletSlide is deferred (needs
// slide-part cloning + rel/content-type fixups).
function emit(file, ops) {
  const zip = new AdmZip(fs.readFileSync(file));
  const MIN_FIX_PT = 24;
  const slideRe = /^ppt\/slides\/slide\d+\.xml$/;
  const masterRe = /^ppt\/slideMasters\/slideMaster\d+\.xml$/;
  for (const op of ops) {
    if (op.op === "raiseFonts") {
      const min = (op.minPt || MIN_FIX_PT) * 100;
      for (const e of zip.getEntries()) {
        if (!slideRe.test(e.entryName)) continue;
        const xml = e
          .getData()
          .toString("utf8")
          .replace(/sz="(\d+)"/g, (m, n) =>
            parseInt(n, 10) < min ? `sz="${min}"` : m,
          );
        zip.updateFile(e.entryName, Buffer.from(xml));
      }
    } else if (op.op === "stripMasterLogo") {
      for (const e of zip.getEntries()) {
        if (!masterRe.test(e.entryName)) continue;
        const xml = e
          .getData()
          .toString("utf8")
          .replace(/<p:pic>[\s\S]*?<\/p:pic>/g, "");
        zip.updateFile(e.entryName, Buffer.from(xml));
      }
    }
    // else: unsupported op ignored (splitOverBulletSlide deferred)
  }
  return zip.toBuffer();
}

export default { id: "pptx", ingest, emit };
