// Builds the minimal.pptx test fixture from readable OOXML templates, seeded with
// known violations. Kept as source-of-truth (a generated binary is awkward in
// git); test.mjs builds it into a temp dir, ingests, and diffs the golden IR.
//
// Seeded findings on the 4-slide deck:
//   slide 1  — title/bookend + speaker notes
//   slide 2  — clean: 3 bullets @28pt, one font (Arial)
//   slide 3  — BAD: 9 bullets @24pt (Bullet-Riddled) + a lone level-1 sub-bullet
//              (Injured Outlines) + a 12pt footnote run (Ant Fonts)
//   slide 4  — exact duplicate of slide 2 (Backtracking)
//   master   — a logo picture (Floodmarks: present on every slide)
import AdmZip from "adm-zip";

const P = "http://schemas.openxmlformats.org/presentationml/2006/main";
const A = "http://schemas.openxmlformats.org/drawingml/2006/main";
const R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const CT = "http://schemas.openxmlformats.org/package/2006/relationships";

const EMU = 914400; // per inch
const off = (x, y) => `<a:off x="${Math.round(x)}" y="${Math.round(y)}"/>`;
const ext = (cx, cy) =>
  `<a:ext cx="${Math.round(cx)}" cy="${Math.round(cy)}"/>`;
const xfrm = (x, y, cx, cy) => `<a:xfrm>${off(x, y)}${ext(cx, cy)}</a:xfrm>`;

function run(text, sz, font = "Arial") {
  return `<a:r><a:rPr lang="en-US" sz="${sz}"><a:latin typeface="${font}"/></a:rPr><a:t>${text}</a:t></a:r>`;
}
// No rPr → font name + size inherited from the theme / master txStyles (real decks).
function runInherit(text) {
  return `<a:r><a:t>${text}</a:t></a:r>`;
}
// bullet: true → explicit buChar · false → explicit buNone · 'inherit' → no bullet
// tag (formatting inherited from the layout, as real decks emit).
function para({ lvl = 0, bullet = false, runs = [] }) {
  const bu =
    bullet === "inherit"
      ? ""
      : bullet
        ? '<a:buChar char="&#8226;"/>'
        : "<a:buNone/>";
  return `<a:p><a:pPr lvl="${lvl}">${bu}</a:pPr>${runs.join("")}</a:p>`;
}
function sp({
  id,
  name,
  ph = null,
  paras = [],
  box = [457200, 457200, 8229600, 1000000],
}) {
  const phTag = ph ? `<p:ph type="${ph}"/>` : "";
  return `<p:sp>
  <p:nvSpPr><p:cNvPr id="${id}" name="${name}"/><p:cNvSpPr/><p:nvPr>${phTag}</p:nvPr></p:nvSpPr>
  <p:spPr>${xfrm(...box)}</p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/>${paras.join("")}</p:txBody>
</p:sp>`;
}
function slideXml(shapes, extra = "") {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="${P}" xmlns:a="${A}" xmlns:r="${R}">
 <p:cSld><p:spTree>
  <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr/>
  ${shapes.join("\n")}
 </p:spTree></p:cSld>
 ${extra}
</p:sld>`;
}
function notesXml(text) {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:p="${P}" xmlns:a="${A}" xmlns:r="${R}">
 <p:cSld><p:spTree>
  <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
  <p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/><p:cNvSpPr/><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
   <p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>${text}</a:t></a:r></a:p></p:txBody></p:sp>
 </p:spTree></p:cSld>
</p:notes>`;
}

// ── The four slides ──────────────────────────────────────────────────────────
const slide1 = slideXml(
  [
    sp({
      id: 2,
      name: "Title",
      ph: "ctrTitle",
      paras: [para({ runs: [runInherit("My Talk")] })],
    }),
    sp({
      id: 3,
      name: "Subtitle",
      ph: "subTitle",
      box: [457200, 1600000, 8229600, 800000],
      paras: [para({ runs: [run("A demo deck", 3000)] })],
    }),
  ],
  '<p:transition spd="med" advTm="5000"><p:fade/></p:transition>',
); // Preroll (auto-advance) + fade
const cleanBody = sp({
  id: 3,
  name: "Body",
  ph: "body",
  box: [457200, 1600000, 8229600, 4000000],
  paras: [
    para({ lvl: 0, bullet: "inherit", runs: [runInherit("First point")] }),
    para({ lvl: 0, bullet: "inherit", runs: [runInherit("Second point")] }),
    para({ lvl: 0, bullet: "inherit", runs: [runInherit("Third point")] }),
  ],
});
const slide2 = slideXml(
  [
    sp({
      id: 2,
      name: "Title",
      ph: "title",
      paras: [para({ runs: [run("Agenda", 3200)] })],
    }),
    cleanBody,
  ],
  '<p:transition spd="fast"><p:fade/></p:transition>',
); // fade (consistent with slide 1 → Soft Transitions)
const badParas = [];
for (let i = 1; i <= 9; i++)
  badParas.push(
    para({ lvl: 0, bullet: true, runs: [run(`Point ${i}`, 2400)] }),
  );
badParas.push(para({ lvl: 0, bullet: false, runs: [run("Note", 2400)] }));
badParas.push(
  para({ lvl: 1, bullet: true, runs: [run("lonely sub-point", 2400)] }),
); // lone sub-bullet
badParas.push(
  para({
    lvl: 0,
    bullet: false,
    runs: [run("tiny footnote source: internal", 1200)],
  }),
); // Ant Fonts
const slide3 = slideXml(
  [
    sp({
      id: 2,
      name: "Title",
      ph: "title",
      paras: [para({ runs: [run("Details", 3200)] })],
    }),
    sp({
      id: 3,
      name: "Body",
      ph: "body",
      box: [457200, 1600000, 8229600, 4600000],
      paras: badParas,
    }),
  ],
  "<p:timing><p:tnLst><p:par><p:cTn><p:childTnLst><p:anim/></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>",
); // build animation → Gradual Consistency
const slide4 = slide2; // exact duplicate → Backtracking

const master = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:p="${P}" xmlns:a="${A}" xmlns:r="${R}">
 <p:cSld><p:spTree>
  <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
  <p:pic>
   <p:nvPicPr><p:cNvPr id="9" name="CompanyLogo"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
   <p:blipFill><a:blip r:embed="rIdLogo"/></p:blipFill>
   <p:spPr>${xfrm(8000000, 60000, 900000, 400000)}</p:spPr>
  </p:pic>
 </p:spTree></p:cSld>
 <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
 <p:txStyles>
  <p:titleStyle><a:lvl1pPr><a:defRPr sz="4400"/></a:lvl1pPr></p:titleStyle>
  <p:bodyStyle><a:lvl1pPr><a:defRPr sz="2800"/></a:lvl1pPr><a:lvl2pPr><a:defRPr sz="2400"/></a:lvl2pPr></p:bodyStyle>
  <p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>
 </p:txStyles>
</p:sldMaster>`;

const presentation = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="${P}" xmlns:a="${A}" xmlns:r="${R}">
 <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdM"/></p:sldMasterIdLst>
 <p:sldIdLst>
  <p:sldId id="256" r:id="rId1"/>
  <p:sldId id="257" r:id="rId2"/>
  <p:sldId id="258" r:id="rId3"/>
  <p:sldId id="259" r:id="rId4"/>
 </p:sldIdLst>
 <p:sldSz cx="9144000" cy="6858000" type="screen4x3"/>
</p:presentation>`;

const rel = (id, type, target) =>
  `<Relationship Id="${id}" Type="${type}" Target="${target}"/>`;
const RT = {
  slide:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
  master:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
  notes:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide",
  image:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
  theme:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
  office:
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
};

const presentationRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="${CT}">
 ${rel("rId1", RT.slide, "slides/slide1.xml")}
 ${rel("rId2", RT.slide, "slides/slide2.xml")}
 ${rel("rId3", RT.slide, "slides/slide3.xml")}
 ${rel("rId4", RT.slide, "slides/slide4.xml")}
 ${rel("rIdM", RT.master, "slideMasters/slideMaster1.xml")}
</Relationships>`;

const slide1Rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="${CT}">${rel("rIdN", RT.notes, "../notesSlides/notesSlide1.xml")}</Relationships>`;

const masterRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="${CT}">${rel("rIdLogo", RT.image, "../media/logo.png")}${rel("rIdTheme", RT.theme, "../theme/theme1.xml")}</Relationships>`;

const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="${CT}">${rel("rId1", RT.office, "ppt/presentation.xml")}</Relationships>`;

const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
 <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
 <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
 <Override PartName="/ppt/slides/slide3.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
 <Override PartName="/ppt/slides/slide4.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
 <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
 <Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
 <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>`;

const theme1 = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="${A}" name="Office Theme">
 <a:themeElements>
  <a:fontScheme name="Office">
   <a:majorFont><a:latin typeface="Arial"/></a:majorFont>
   <a:minorFont><a:latin typeface="Calibri"/></a:minorFont>
  </a:fontScheme>
 </a:themeElements>
</a:theme>`;

export function buildMinimalPptx() {
  const zip = new AdmZip();
  zip.addFile("[Content_Types].xml", Buffer.from(contentTypes));
  zip.addFile("_rels/.rels", Buffer.from(rootRels));
  zip.addFile("ppt/presentation.xml", Buffer.from(presentation));
  zip.addFile("ppt/_rels/presentation.xml.rels", Buffer.from(presentationRels));
  zip.addFile("ppt/slides/slide1.xml", Buffer.from(slide1));
  zip.addFile("ppt/slides/slide2.xml", Buffer.from(slide2));
  zip.addFile("ppt/slides/slide3.xml", Buffer.from(slide3));
  zip.addFile("ppt/slides/slide4.xml", Buffer.from(slide4));
  zip.addFile("ppt/slides/_rels/slide1.xml.rels", Buffer.from(slide1Rels));
  zip.addFile("ppt/slideMasters/slideMaster1.xml", Buffer.from(master));
  zip.addFile(
    "ppt/slideMasters/_rels/slideMaster1.xml.rels",
    Buffer.from(masterRels),
  );
  zip.addFile("ppt/theme/theme1.xml", Buffer.from(theme1));
  zip.addFile(
    "ppt/notesSlides/notesSlide1.xml",
    Buffer.from(notesXml("Opening remarks — welcome everyone.")),
  );
  zip.addFile("ppt/media/logo.png", Buffer.from([0x89, 0x50, 0x4e, 0x47])); // placeholder bytes (parser reads the ref, not the pixels)
  return zip.toBuffer();
}
