// Render every route and every selection from a data.js, check output, links and live feedback targets.
// Run: node site/tests/render.test.js [path/to/data.js] [--svg OUTDIR]
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const G = require("../js/graph.js");
global.G = G;
const V = require("../js/views.js");

const args = process.argv.slice(2);
const dataPath =
  args.find((a) => a.endsWith(".js")) ||
  path.join(__dirname, "../data/data.js");
const svgOut = args.includes("--svg") ? args[args.indexOf("--svg") + 1] : null;
const sandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(dataPath, "utf8"), sandbox);
const D = sandbox.window.ORG_DATA;
const fails = [];
const fail = (m) => fails.push(m);

// -- a live run in flight, made from the newest real run, so live states and feedback are exercised
const base = (D.live.runs || [])[0];
if (base) {
  const run = JSON.parse(JSON.stringify(base));
  run.id = "rsim";
  run.status = "running";
  run.end_status = null;
  const keys = Object.keys(run.tasks);
  const k = keys.find((x) => x.includes("/")) || keys[0];
  run.tasks[k].state = "running";
  run.current = [
    {
      key: k,
      wf: run.tasks[k].wf,
      rel: run.tasks[k].rel,
      since: D.live.at - 42,
      usd: 0.1,
    },
  ];
  run.change = {
    worktree: "/tmp/x",
    files: [{ status: "M", path: "workflows/tdd-unit.yaml" }],
    rungs: { highest: "protected", rows: [], refused: 1 },
  };
  D.live.runs.unshift(run);
}

function check(route, html) {
  for (const bad of ["undefined", '="NaN', "NaN,", "NaN ", "[object"])
    if (html.replace(/NaN or deep|payload NaN/g, "").includes(bad))
      fail(
        `${route}: output contains ${bad}: ...${html.slice(Math.max(0, html.indexOf(bad) - 80), html.indexOf(bad) + 40)}`,
      );
  if (/[\u2013\u2014]/.test(html)) fail(`${route}: en or em dash in output`);
  const open = (html.match(/<svg\b/g) || []).length,
    close = (html.match(/<\/svg>/g) || []).length;
  if (open !== close) fail(`${route}: ${open} <svg> vs ${close} </svg>`);
  if (/<a [^>]*href="(?!#|https?:)/.test(html)) {
    const m = html.match(/<a [^>]*href="((?!#|https?:)[^"]*)"/);
    fail(`${route}: link outside the hash routes: ${m && m[1]}`);
  }
}

const seen = new Set();
const queue = V.routes(D).slice();
// every selectable thing
for (const [wf, w] of Object.entries(D.workflows)) {
  for (const n of V.walk(w.tree)) queue.push(V.wfHref(wf, { sel: n.key }));
  queue.push(
    V.wfHref(wf, {
      ops: true,
      sel: "step:" + V.walk(w.tree).find((n) => !n.children && !n.branches).key,
    }),
  );
}
for (const u of D.build.units)
  queue.push("#/build/" + encodeURIComponent(u.id));
for (const s of D.language.sections) queue.push("#/language/" + s.id);
for (const d of D.decisions.items) queue.push("#/decisions/" + d.id);
for (const r of D.live.runs || [])
  for (const wf of r.workflows || [r.workflow])
    if (D.workflows[wf]) {
      queue.push(V.wfHref(wf, { run: r.id }));
      queue.push(V.wfHref(wf, { run: r.id, ops: true }));
    }

let rendered = 0;
while (queue.length) {
  const h = queue.shift();
  if (seen.has(h)) continue;
  seen.add(h);
  const r = V.parse(h);
  if (r.view === "notfound") {
    fail(`${h}: does not parse`);
    continue;
  }
  let html, wide;
  for (const width of [390, 1200]) {
    try {
      html = V.render(r, D, { width, now: D.live.at });
      if (width === 390) wide = html;
    } catch (e) {
      fail(`${h}: throws ${e.stack.split("\n").slice(0, 3).join(" ")}`);
      continue;
    }
    if (html.includes("Nothing here")) fail(`${h}: renders as not found`);
    check(h, html);
  }
  rendered++;
  if (!html) continue;
  for (const m of html.matchAll(/href="(#[^"]*)"/g)) {
    const link = m[1].replace(/&amp;/g, "&");
    if (!seen.has(link)) queue.push(link);
  }
  if (svgOut && r.sel == null && rendered < 400) {
    (html.match(/<svg xmlns[^>]*class="graph"[\s\S]*?<\/svg>/g) || [])
      .slice(0, 1)
      .forEach((s) => writeSvg(h, s));
    (wide.match(/<svg xmlns[^>]*class="graph"[\s\S]*?<\/svg>/g) || [])
      .slice(0, 1)
      .forEach((s) => writeSvg(h + "_phone", s));
  }
}

// -- live states and feedback hit nodes and edges that exist
if (base) {
  const run = D.live.runs[0],
    wf = run.workflow,
    cur = run.current[0];
  const cases = [
    ["#/", { token: { type: "trigger", wf } }],
    ["#/", { token: { type: "start", wf, rel: cur.rel, key: cur.key } }],
    ["#/s/" + D.org.items[wf].seg, { token: { type: "trigger", wf } }],
    [
      V.wfHref(wf),
      { token: { type: "start", wf, rel: cur.rel, key: cur.key } },
    ],
    [
      V.wfHref(wf),
      { token: { type: "rework", wf, rel: cur.rel, key: cur.key } },
    ],
    [
      V.wfHref(wf, { ops: true }),
      { token: { type: "accept", ok: false, wf, rel: cur.rel, key: cur.key } },
    ],
  ];
  for (const [h, ev] of cases) {
    const r = V.parse(h),
      html = V.render(r, D, { width: 1200, now: D.live.at });
    const st = V.liveStates(r, D, D.live.at);
    if (!Object.keys(st).length)
      fail(`${h}: no live state while a run is in flight`);
    for (const id of Object.keys(st))
      if (!html.includes(`data-node="${G.esc(id)}"`))
        fail(`${h}: live state for missing node ${id}`);
    const acts = V.feedback(r, D, ev, run);
    if (!acts.length) fail(`${h}: no feedback for ${ev.token.type}`);
    for (const a of acts) {
      if (a.edge && !html.includes(`data-edge="${G.esc(a.edge)}"`))
        fail(`${h}: feedback edge ${a.edge} not drawn`);
      if (a.node && !html.includes(`data-node="${G.esc(a.node)}"`))
        fail(`${h}: feedback node ${a.node} not drawn`);
      if (a.prefix && !html.includes(`data-edge="${G.esc(a.prefix)}`))
        fail(`${h}: no edge with prefix ${a.prefix}`);
    }
  }
  const home = V.render(V.parse("#/"), D, { width: 1200, now: D.live.at });
  const K = V.critical(D, D.live.at);
  const slotCount = (cls) => {
    const m = home.match(
      new RegExp('class="slot ' + cls + '[^"]*"><h2>[\\s\\S]*?</h2>'),
    );
    const n = m && m[0].match(/class="n">(\d+)</);
    return n ? +n[1] : -1;
  };
  if (
    slotCount("s-build") !== K.building.length ||
    slotCount("s-owner") !== K.owner.length ||
    slotCount("s-fail") !== K.failing.length
  )
    fail(
      `home band counts ${slotCount("s-build")}/${slotCount("s-owner")}/${slotCount("s-fail")} differ from the sidebar lists ${K.building.length}/${K.owner.length}/${K.failing.length}`,
    );
  if (!home.includes("Building now") || !home.includes(wf))
    fail("home: the running run is not listed under building now");
}

// -- goal first: every step, group and unit panel opens with a non-empty goal; segment and workflow views state theirs under the title
const GOAL =
  /<a class="close"[^>]*>Close<\/a><\/div><div class="goal"><b>Goal<\/b><p>([^<]*)<\/p>/;
for (const [wf, w] of Object.entries(D.workflows)) {
  for (const n of V.walk(w.tree)) {
    const html = V.render(V.parse(V.wfHref(wf, { sel: n.key })), D, {
      width: 1200,
    });
    const m = html.match(GOAL);
    if (!m || !m[1].trim() || /No goal is written/.test(m[1]))
      fail(
        `${wf} ${n.key}: the panel does not open with a goal (${m ? m[1] : "no goal box right after the title"})`,
      );
  }
  const top = V.render(V.parse(V.wfHref(wf)), D, { width: 1200 });
  if (
    !/<\/h1><p class="lead">[\s\S]*?<div class="goal"><b>Goal<\/b><p>[^<]+<\/p>/.test(
      top,
    )
  )
    fail(`${wf}: no goal under the title`);
}
for (const s of D.org.segments)
  if (
    !/<div class="goal"><b>Goal<\/b><p>[^<]+</.test(
      V.render(V.parse("#/s/" + s.id), D, { width: 1200 }),
    )
  )
    fail(`segment ${s.id}: no goal under the title`);
for (const u of D.build.units) {
  const m = V.render(V.parse("#/build/" + u.id), D, { width: 1200 }).match(
    GOAL,
  );
  if (!m || !m[1].trim()) fail(`unit ${u.id}: no goal in its panel`);
}

// -- path highlight: every edge with ends names nodes drawn in the same graph
for (const h of V.routes(D)) {
  const html = V.render(V.parse(h), D, { width: 1200 });
  for (const g of html.match(/<svg xmlns[^>]*class="graph"[\s\S]*?<\/svg>/g) ||
    []) {
    const ids = new Set(
      [...g.matchAll(/data-node="([^"]*)"/g)].map((m) => m[1]),
    );
    for (const m of g.matchAll(/data-from="([^"]*)" data-to="([^"]*)"/g))
      for (const end of [m[1], m[2]])
        if (!ids.has(end)) fail(`${h}: edge end ${end} is not a drawn node`);
  }
  if (
    /<ul class="legend"/.test(html) &&
    !/<button type="button" data-filter="[^"]+" aria-pressed="false">/.test(
      html,
    )
  )
    fail(`${h}: legend entries are not filter buttons`);
  const up = V.parent(V.parse(h), D);
  if (up && V.parse(up).view === "notfound")
    fail(`${h}: parent ${up} does not parse`);
}

// -- jump palette: every entry opens a real view
const idx = V.searchIndex(D);
if (idx.length < Object.keys(D.workflows).length + D.build.units.length)
  fail("palette index is missing entries");
for (const x of idx) {
  const r = V.parse(x.href);
  if (
    r.view === "notfound" ||
    V.render(r, D, { width: 1200 }).includes("Nothing here")
  )
    fail(
      `palette entry ${x.label} goes to ${x.href}, which renders as not found`,
    );
  if (!x.label || !x.sub)
    fail(`palette entry without a label or kind: ${JSON.stringify(x)}`);
}
for (const wf of Object.keys(D.workflows))
  if (!idx.some((x) => x.href === V.wfHref(wf)))
    fail(`palette lacks workflow ${wf}`);

// -- folded groups: a folded container is one node with an unfold button, and the flow still renders
for (const [wf, w] of Object.entries(D.workflows)) {
  const cont = V.walk(w.tree).filter((n) => n.children || n.branches);
  if (!cont.length) continue;
  const all = {};
  cont.forEach((n) => {
    all[n.key] = true;
  });
  const open = V.render(V.parse(V.wfHref(wf)), D, { width: 1200 }),
    shut = V.render(V.parse(V.wfHref(wf)), D, { width: 1200, collapsed: all });
  check(V.wfHref(wf) + " folded", shut);
  const count = (h) => (h.match(/class="node /g) || []).length;
  if (!(count(shut) < count(open)))
    fail(`${wf}: folding every group does not reduce the nodes`);
  const top = cont.filter(
    (n) => !cont.some((p) => p !== n && n.key.startsWith(p.key + "/")),
  );
  for (const n of top)
    if (!shut.includes(`data-toggle="${G.esc(n.key)}" aria-expanded="false"`))
      fail(`${wf}: folded ${n.key} has no unfold button`);
}

// -- magnitude: a run graph sizes steps by cost and marks rounds
if (base) {
  const r0 = D.live.runs.find(
    (r) =>
      r.status !== "running" &&
      Object.values(r.tasks).some((t) => t.starts > 1),
  );
  if (r0) {
    const html = V.render(V.parse(V.wfHref(r0.workflow, { run: r0.id })), D, {
      width: 1200,
    });
    if (!/class="tick"/.test(html))
      fail(`run ${r0.id}: no round ticks on steps that ran more than once`);
    if (
      new Set(
        [...html.matchAll(/<circle class="disc" r="(\d+)"/g)].map((m) => m[1]),
      ).size < 2
    )
      fail(`run ${r0.id}: step size does not vary with cost`);
  }
}

// -- a run without its cost journal says its cost is partial, on the home and in its run box
if (base) {
  const keep = JSON.parse(JSON.stringify(D.live.runs));
  const pr = JSON.parse(JSON.stringify(D.live.runs[D.live.runs.length - 1]));
  pr.id = "rpartial";
  pr.cost_partial = true;
  pr.cost_src = "ledger";
  pr.status = "running";
  pr.end_status = null;
  pr.started = D.live.at + 5;
  pr.last = D.live.at + 6; // the newest run of its workflow, so the latest-state views show it
  D.live.runs.push(pr);
  if (!V.render(V.parse("#/"), D, { width: 1200 }).includes("cost partial"))
    fail("home: a run with partial cost does not say cost partial");
  if (
    !V.render(V.parse(V.wfHref(pr.workflow, { run: "rpartial" })), D, {
      width: 1200,
    }).includes("cost, partial")
  )
    fail("run box: partial cost is not labelled");
  D.live.runs = keep;
}

// -- latest state only: a later run of the same workflow supersedes an older failure; old runs leave the default views
if (base) {
  const keep = D.live.runs;
  const mk = (id, st, t, status) =>
    Object.assign(JSON.parse(JSON.stringify(base)), {
      id,
      run_id: id + "000000",
      status: status || "ended",
      end_status: st,
      started: t,
      last: t + 1,
      current: [],
    });
  const wf = base.workflow;
  D.live.runs = [
    mk("rold1", "error", 10),
    mk("rold2", "error", 20),
    mk("rnew", "success", 30),
  ];
  let K = V.critical(D, D.live.at),
    home = V.render(V.parse("#/"), D, { width: 1200, now: D.live.at });
  if (K.failing.some((x) => x.includes(wf)))
    fail(
      "projection: a failure superseded by a later successful run still counts as failing",
    );
  if (
    (home.match(/<ul class="runs">([\s\S]*?)<\/ul>/) || ["", ""])[1].split(
      "<li>",
    ).length -
      1 !==
    1
  )
    fail("projection: home lists more than the latest run of a workflow");
  if (/rold/.test(home)) fail("projection: an old run is linked from the home");
  const wv = V.render(V.parse(V.wfHref(wf)), D, {
    width: 1200,
    now: D.live.at,
  });
  if (/rold/.test(wv.match(/<nav class="runpick"[\s\S]*?<\/nav>/)[0]))
    fail("projection: the run picker lists a superseded run");
  const rv = V.render(V.parse(V.wfHref(wf, { run: "rnew" })), D, {
    width: 1200,
    now: D.live.at,
  });
  const hist = rv.match(
    /<details class="hist"><summary>([^<]*)<\/summary>([\s\S]*?)<\/details>/,
  );
  if (
    !hist ||
    !/2 other runs/.test(hist[1]) ||
    !/rold1/.test(hist[2]) ||
    / open>/.test(hist[0])
  )
    fail(
      "projection: the run box has no collapsed history of the 2 older runs",
    );
  const ov = V.render(V.parse(V.wfHref(wf, { run: "rold1" })), D, {
    width: 1200,
    now: D.live.at,
  });
  if (ov.includes("Nothing here") || !/superseded/.test(ov))
    fail(
      "projection: an old run's link no longer opens, or is not marked superseded",
    );
  D.live.runs = [mk("rok", "success", 10), mk("rbad", "error", 20)];
  K = V.critical(D, D.live.at);
  if (K.failing.filter((x) => x.includes(wf)).length !== 1)
    fail("projection: the latest run failed but Failing does not list it once");
  D.live.runs = [mk("rbad2", "error", 10), mk("rrun", null, 20, "running")];
  K = V.critical(D, D.live.at);
  if (K.failing.some((x) => x.includes(wf)))
    fail("projection: a running retry does not supersede the failed run");
  D.live.runs = keep;
}

// -- build: band counts, sidebar lists and the unit graph read the same projected units
{
  const U = D.build.units,
    C = D.org.critical,
    K = V.critical(D, D.live.at);
  const bv = V.render(V.parse("#/build"), D, { width: 1200, now: D.live.at });
  const cnt = (cls, h) => {
    const m = h.match(
      new RegExp(
        'class="slot ' + cls + '[^"]*"><h2>[\\s\\S]*?class="n">(\\d+)<',
      ),
    );
    return m ? +m[1] : -1;
  };
  const act = U.filter((u) => u.st === "active").length,
    own = U.filter((u) => u.st === "gate").length,
    bad = U.filter((u) => u.st === "failed").length;
  if (cnt("s-build", bv) !== act)
    fail(
      `build: being built shows ${cnt("s-build", bv)}, ${act} units are active`,
    );
  if (cnt("s-owner", bv) !== own)
    fail(
      `build: needs you shows ${cnt("s-owner", bv)}, ${own} units wait for the owner`,
    );
  if (cnt("s-fail", bv) !== bad + C.failing.length)
    fail(
      `build: failing shows ${cnt("s-fail", bv)}, wanted ${bad + C.failing.length}`,
    );
  if (
    D.org.totals.done !== U.filter((u) => u.st === "done").length ||
    D.org.totals.units !== U.length
  )
    fail("build: org totals differ from the projected units");
  for (const u of U) {
    if (!bv.includes(`data-node="${u.id}"`))
      fail(`build: unit ${u.id} is not drawn`);
    if (
      u.st === "active" &&
      !K.building.some((x) => x.includes(`#/build/${u.id}"`))
    )
      fail(`sidebar: active unit ${u.id} not under building`);
    if (u.st === "gate" && !K.owner.some((x) => x.includes(`#/build/${u.id}"`)))
      fail(`sidebar: unit ${u.id} that needs the owner is not under needs you`);
    if (
      u.st === "failed" &&
      !K.failing.some((x) => x.includes(`#/build/${u.id}"`))
    )
      fail(`sidebar: failed unit ${u.id} is not under failing`);
    if (
      u.conflict &&
      !V.render(V.parse("#/build/" + u.id), D, { width: 1200 }).includes(
        G.esc(u.conflict),
      )
    )
      fail(`unit ${u.id}: its conflict with GitHub is not shown`);
  }
  if ((D.build.ingest || {}).events && !U.some((u) => u.state_src === "ingest"))
    fail(
      "build: the ingest log has reports but no unit takes its state from it",
    );
}

// -- metrics: the latest org.metric value, else no collector
{
  const wf = Object.keys(D.workflows).find(
    (w) => D.workflows[w].metrics.length,
  );
  if (wf) {
    const id = D.workflows[wf].metrics[0].id,
      keep = D.live.metrics;
    D.live.metrics = {};
    if (
      !V.render(V.parse(V.wfHref(wf)), D, { width: 1200 }).includes(
        "no collector",
      )
    )
      fail("metrics: a metric without entries does not say no collector");
    D.live.metrics = {
      [id]: { metric: id, value: 0.42, reason: "from the test", at: 1, seq: 1 },
    };
    const h = V.render(V.parse(V.wfHref(wf)), D, { width: 1200 }),
      home = V.render(V.parse("#/"), D, { width: 1200 });
    if (
      !h.includes("0.42, from the test") ||
      !home.includes("0.42, from the test")
    )
      fail(
        "metrics: the latest value is not shown on the workflow and the home",
      );
    D.live.metrics = keep;
  }
}

// -- route parsing
const pr = V.parse(
  "#/w/tdd-unit/r/rsim/ops/n/" + encodeURIComponent("acc:cycle/red:0"),
);
if (
  pr.wf !== "tdd-unit" ||
  pr.run !== "rsim" ||
  !pr.ops ||
  pr.sel !== "acc:cycle/red:0"
)
  fail("parse: nested selection " + JSON.stringify(pr));
if (V.parse("#/w/tdd-unit/n/cycle/red").sel !== "cycle/red")
  fail("parse: unencoded nested key");
if (V.parse("#/nope").view !== "notfound")
  fail("parse: unknown route accepted");

// -- layout: no two nodes of a layer overlap
const lay = G.layered(
  [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }],
  [
    { from: "a", to: "b" },
    { from: "a", to: "c" },
    { from: "c", to: "d" },
    { from: "d", to: "a" },
  ],
  { dir: "LR" },
);
const ps = Object.values(lay.pos);
for (let i = 0; i < ps.length; i++)
  for (let j = i + 1; j < ps.length; j++)
    if (ps[i].x === ps[j].x && ps[i].y === ps[j].y)
      fail("layout: overlapping nodes");
if (lay.pos.b.layer !== 1 || lay.pos.d.layer !== 2)
  fail("layout: layers " + JSON.stringify(lay.pos));

function writeSvg(h, s) {
  fs.mkdirSync(svgOut, { recursive: true });
  const css = fs.readFileSync(path.join(__dirname, "../css/site.css"), "utf8");
  const vars = {};
  const rootBlock = css.match(/:root \{([\s\S]*?)\}/)[1];
  for (const m of rootBlock.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g))
    vars[m[1]] = m[2].trim();
  let sheet = css.slice(
    css.indexOf(
      "/* ------------------------------------------------------------ svg graph */",
    ),
    css.indexOf(
      "/* ------------------------------------------------------------ blocks */",
    ),
  );
  sheet = sheet
    .replace(/var\(--([a-z0-9-]+)\)/g, (_, k) => vars[k] || "#000")
    .replace(/color-mix\([^)]*\)/g, "#f4f5f2");
  const name = h.replace(/[^a-z0-9]+/gi, "_").replace(/^_+/, "") || "home";
  const out = s.replace(
    /<defs>/,
    `<style>text{font-family:sans-serif}${sheet}</style><rect width="100%" height="100%" fill="#ffffff"/><defs>`,
  );
  fs.writeFileSync(path.join(svgOut, name + ".svg"), out);
}

console.log(`routes rendered: ${rendered}, links followed: ${seen.size}`);
if (fails.length) {
  console.log("FAIL");
  for (const f of fails.slice(0, 60)) console.log("  - " + f);
  process.exit(1);
}
console.log("PASS");
