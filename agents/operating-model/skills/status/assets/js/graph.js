/* Graph layout and SVG drawing. Pure functions: no DOM access, so node can load this file for tests. */
(function (root) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Width of a text run in px. Generous so labels are never clipped.
  function tw(s, size) {
    return String(s || "").length * (size || 14) * 0.56 + 2;
  }

  function wrap(s, n) {
    var out = [],
      cur = "";
    String(s || "")
      .split(/\s+/)
      .forEach(function (w) {
        if (!w) return;
        if (cur && cur.length + 1 + w.length > n) {
          out.push(cur);
          cur = w;
        } else {
          cur = cur ? cur + " " + w : w;
        }
      });
    if (cur) out.push(cur);
    return out.length ? out : [""];
  }

  // ------------------------------------------------------------------ layered layout
  // nodes: [{id, layer?}], edges: [{from, to}]. Layer = given layer, else the longest path from a source.
  // Order inside a layer: a few barycenter sweeps. Returns positions of node centers.
  function layered(nodes, edges, opt) {
    opt = opt || {};
    var dir = opt.dir || "LR",
      gm = opt.gapMain || 220,
      gc = opt.gapCross || 120,
      pad = opt.pad || 70;
    var ids = nodes.map(function (n) {
      return n.id;
    });
    var has = {};
    ids.forEach(function (i) {
      has[i] = true;
    });
    var E = edges.filter(function (e) {
      return has[e.from] && has[e.to] && e.from !== e.to && !e.noLayout;
    });
    var layer = {};
    nodes.forEach(function (n) {
      if (n.layer != null) layer[n.id] = n.layer;
    });
    // drop back edges found by a DFS that starts from the sources, so a cycle never pushes its entry down
    var out = {},
      indeg = {};
    ids.forEach(function (i) {
      out[i] = [];
      indeg[i] = 0;
    });
    E.forEach(function (e) {
      out[e.from].push(e);
      indeg[e.to]++;
    });
    var state = {},
      back = [];
    function dfs(id) {
      state[id] = 1;
      out[id].forEach(function (e) {
        if (state[e.to] === 1) back.push(e);
        else if (!state[e.to]) dfs(e.to);
      });
      state[id] = 2;
    }
    ids
      .filter(function (i) {
        return !indeg[i];
      })
      .concat(ids)
      .forEach(function (i) {
        if (!state[i]) dfs(i);
      });
    E = E.filter(function (e) {
      return back.indexOf(e) < 0;
    });
    var preds = {};
    ids.forEach(function (i) {
      preds[i] = [];
    });
    E.forEach(function (e) {
      preds[e.to].push(e.from);
    });
    function L(id) {
      if (layer[id] != null) return layer[id];
      var m = -1;
      preds[id].forEach(function (p) {
        m = Math.max(m, L(p));
      });
      layer[id] = m + 1;
      return layer[id];
    }
    ids.forEach(L);
    var nl = 0;
    ids.forEach(function (i) {
      nl = Math.max(nl, layer[i] + 1);
    });
    var rows = [];
    for (var k = 0; k < nl; k++) rows.push([]);
    ids.forEach(function (i) {
      rows[layer[i]].push(i);
    });
    var idx = {};
    function index() {
      rows.forEach(function (r) {
        r.forEach(function (id, j) {
          idx[id] = j;
        });
      });
    }
    index();
    var nb = {};
    ids.forEach(function (i) {
      nb[i] = { up: [], down: [] };
    });
    E.forEach(function (e) {
      nb[e.to].up.push(e.from);
      nb[e.from].down.push(e.to);
    });
    function bary(id, side) {
      var xs = nb[id][side];
      if (!xs.length) return idx[id];
      var s = 0;
      xs.forEach(function (x) {
        s += idx[x];
      });
      return s / xs.length;
    }
    for (var it = 0; it < 4; it++) {
      for (var a = 1; a < nl; a++) {
        sortBy(rows[a], "up");
      }
      for (var b = nl - 2; b >= 0; b--) {
        sortBy(rows[b], "down");
      }
    }
    function sortBy(r, side) {
      var key = {};
      r.forEach(function (id) {
        key[id] = bary(id, side);
      });
      r.sort(function (p, q) {
        return key[p] - key[q] || idx[p] - idx[q];
      });
      r.forEach(function (id, j) {
        idx[id] = j;
      });
    }
    var maxN = 0;
    rows.forEach(function (r) {
      maxN = Math.max(maxN, r.length);
    });
    var pos = {};
    rows.forEach(function (r, li) {
      var off = ((maxN - r.length) * gc) / 2;
      r.forEach(function (id, j) {
        var main = pad + li * gm,
          cross = pad + off + j * gc;
        pos[id] =
          dir === "LR"
            ? { x: main, y: cross, layer: li, order: j }
            : { x: cross, y: main, layer: li, order: j };
      });
    });
    var w = dir === "LR" ? pad * 2 + (nl - 1) * gm : pad * 2 + (maxN - 1) * gc;
    var h = dir === "LR" ? pad * 2 + (maxN - 1) * gc : pad * 2 + (nl - 1) * gm;
    return {
      pos: pos,
      w: Math.max(w, 0),
      h: Math.max(h, 0),
      layers: nl,
      rows: rows,
    };
  }

  // Cubic edge between two circles, leaving along the main axis.
  function edgePath(a, b, dir, ra, rb, bend) {
    ra = ra || 24;
    rb = rb || 24;
    bend = bend || 0;
    var dx = b.x - a.x,
      dy = b.y - a.y;
    var horiz =
      dir === "LR"
        ? Math.abs(dx) >= Math.abs(dy) * 0.3 || Math.abs(dx) > 40
        : Math.abs(dy) < Math.abs(dx) * 0.3 && Math.abs(dy) < 40;
    var sx, sy, ex, ey, c1x, c1y, c2x, c2y;
    if (dir === "LR" && Math.abs(dx) < 40) {
      // same layer, stacked: arc out to the left so the edge stays clear of the labels under the nodes
      var u = dy >= 0 ? 1 : -1,
        off = 120;
      sx = a.x - ra * 0.7;
      sy = a.y + u * ra * 0.7;
      ex = b.x - (rb + 4) * 0.7;
      ey = b.y - u * (rb + 4) * 0.7;
      c1x = sx - off;
      c1y = sy + u * 20;
      c2x = ex - off;
      c2y = ey - u * 20;
    } else if (horiz) {
      var s = dx >= 0 ? 1 : -1;
      sx = a.x + s * ra;
      sy = a.y + bend;
      ex = b.x - s * (rb + 6);
      ey = b.y + bend;
      var m = Math.max(40, Math.abs(ex - sx) / 2);
      c1x = sx + s * m;
      c1y = sy;
      c2x = ex - s * m;
      c2y = ey;
    } else {
      var t = dy >= 0 ? 1 : -1;
      sx = a.x + bend;
      sy = a.y + t * ra;
      ex = b.x + bend;
      ey = b.y - t * (rb + 6);
      var m2 = Math.max(30, Math.abs(ey - sy) / 2);
      c1x = sx;
      c1y = sy + t * m2;
      c2x = ex;
      c2y = ey - t * m2;
    }
    return {
      d:
        "M" +
        r1(sx) +
        "," +
        r1(sy) +
        " C" +
        r1(c1x) +
        "," +
        r1(c1y) +
        " " +
        r1(c2x) +
        "," +
        r1(c2y) +
        " " +
        r1(ex) +
        "," +
        r1(ey),
      mid: {
        x: (sx + 3 * c1x + 3 * c2x + ex) / 8,
        y: (sy + 3 * c1y + 3 * c2y + ey) / 8,
      },
    };
  }
  function r1(v) {
    return Math.round(v * 10) / 10;
  }

  // ------------------------------------------------------------------ node glyphs
  // Every node carries every state glyph; the class st-<state> shows one. Live updates only swap the class.
  var STATES = [
    "done",
    "active",
    "gate",
    "queued",
    "failed",
    "skipped",
    "escalated",
    "model",
    "code",
    "human",
    "event",
    "role",
    "check",
    "rubric",
    "interrupted",
  ];
  function glyphs(r) {
    var k = r / 22;
    function s(v) {
      return r1(v * k);
    }
    return (
      '<g class="gl gl-done"><path d="M' +
      s(-8) +
      ",0 l" +
      s(5.5) +
      "," +
      s(6) +
      " l" +
      s(10) +
      "," +
      s(-12) +
      '"/></g>' +
      '<g class="gl gl-active"><circle class="spin" r="' +
      s(11) +
      '"/></g>' +
      '<g class="gl gl-gate"><rect x="' +
      s(-7) +
      '" y="' +
      s(-2) +
      '" width="' +
      s(14) +
      '" height="' +
      s(11) +
      '" rx="' +
      s(2) +
      '"/><path d="M' +
      s(-4.5) +
      "," +
      s(-2) +
      " v" +
      s(-4) +
      " a" +
      s(4.5) +
      "," +
      s(4.5) +
      " 0 0 1 " +
      s(9) +
      ",0 v" +
      s(4) +
      '"/></g>' +
      '<g class="gl gl-failed"><path d="M' +
      s(-7) +
      "," +
      s(-7) +
      " L" +
      s(7) +
      "," +
      s(7) +
      " M" +
      s(7) +
      "," +
      s(-7) +
      " L" +
      s(-7) +
      "," +
      s(7) +
      '"/></g>' +
      '<g class="gl gl-skipped"><path d="M' +
      s(-8) +
      ",0 H" +
      s(8) +
      '"/></g>' +
      '<g class="gl gl-interrupted"><path d="M' +
      s(-5) +
      "," +
      s(-7) +
      " V" +
      s(7) +
      " M" +
      s(5) +
      "," +
      s(-7) +
      " V" +
      s(7) +
      '"/></g>' +
      '<g class="gl gl-escalated"><path d="M0,' +
      s(8) +
      " V" +
      s(-7) +
      " M" +
      s(-6) +
      "," +
      s(-1) +
      " L0," +
      s(-7) +
      " L" +
      s(6) +
      "," +
      s(-1) +
      '"/></g>' +
      '<g class="gl gl-model"><circle r="' +
      s(5) +
      '"/></g>' +
      '<g class="gl gl-code"><rect x="' +
      s(-5) +
      '" y="' +
      s(-5) +
      '" width="' +
      s(10) +
      '" height="' +
      s(10) +
      '" rx="' +
      s(1.5) +
      '"/></g>' +
      '<g class="gl gl-human"><rect x="' +
      s(-7) +
      '" y="' +
      s(-2) +
      '" width="' +
      s(14) +
      '" height="' +
      s(11) +
      '" rx="' +
      s(2) +
      '"/><path d="M' +
      s(-4.5) +
      "," +
      s(-2) +
      " v" +
      s(-4) +
      " a" +
      s(4.5) +
      "," +
      s(4.5) +
      " 0 0 1 " +
      s(9) +
      ",0 v" +
      s(4) +
      '"/></g>'
    );
  }

  // Fit a label into maxw px at a font size: cut at a word or character and add an ellipsis. The full text
  // stays in the node's <title>, so nothing is lost; the font never shrinks below its level's size.
  function fit(s, maxw, size) {
    s = String(s || "");
    if (!maxw || tw(s, size) <= maxw) return s;
    var n = Math.max(3, Math.floor((maxw - 2) / ((size || 14) * 0.56)) - 1);
    return s.slice(0, n).replace(/[\s,.:;/-]+$/, "") + "…";
  }
  var LV = { 1: 17, 2: 15, 3: 14 }; // label size per hierarchy level; sub lines are 12.5
  function shapePath(shape, r) {
    if (shape === "diamond")
      return (
        '<path class="disc" d="M0,' +
        -r +
        " L" +
        r +
        ",0 L0," +
        r +
        " L" +
        -r +
        ',0 Z"/>'
      );
    if (shape === "square")
      return (
        '<rect class="disc" x="' +
        -r +
        '" y="' +
        -r +
        '" width="' +
        2 * r +
        '" height="' +
        2 * r +
        '" rx="' +
        r1(r * 0.28) +
        '"/>'
      );
    if (shape === "hex") {
      var pts = [];
      for (var i = 0; i < 6; i++) {
        var a = (Math.PI / 3) * i;
        pts.push(r1(Math.cos(a) * r * 1.08) + "," + r1(Math.sin(a) * r * 1.08));
      }
      return '<path class="disc" d="M' + pts.join(" L") + ' Z"/>';
    }
    if (shape === "tag")
      return (
        '<path class="disc" d="M' +
        r1(-r) +
        "," +
        r1(-r * 0.72) +
        " H" +
        r1(r * 0.3) +
        " L" +
        r +
        ",0 L" +
        r1(r * 0.3) +
        "," +
        r1(r * 0.72) +
        " H" +
        r1(-r) +
        ' Z"/>'
      );
    return '<circle class="disc" r="' + r + '"/>';
  }

  // n: {id, x, y, r, st, kind, seg, label, sub, href, title, floor, faded, shape, labelPos, lv,
  //     ring (0..1 progress), ticks (attempts), badge (a count), heat (0..1 tint), maxw (label width), cls}
  function node(n) {
    var r = n.r || 22,
      x = r1(n.x),
      y = r1(n.y),
      lv = n.lv || 3,
      fs = LV[lv];
    var cls =
      "node st-" +
      (n.st || "queued") +
      " lv" +
      lv +
      (n.kind ? " k-" + n.kind : "") +
      (n.seg ? " seg-" + n.seg : "") +
      (n.floor ? " floor" : "") +
      (n.faded ? " faded" : "") +
      (n.shape ? " sh-" + n.shape : "") +
      (n.cls ? " " + n.cls : "");
    var style =
      n.heat != null
        ? ' style="--heat:' +
          Math.round(Math.max(0, Math.min(1, n.heat)) * 100) / 100 +
          '"'
        : "";
    var ring = n.floor ? '<circle class="fring" r="' + (r + 4) + '"/>' : "";
    if (n.ring != null) {
      var rr = r + (n.floor ? 9 : 6),
        pct = Math.round(Math.max(0, Math.min(1, n.ring)) * 100);
      ring +=
        '<circle class="track" r="' +
        rr +
        '"/><circle class="prog" r="' +
        rr +
        '" pathLength="100" stroke-dasharray="' +
        pct +
        ' 100" transform="rotate(-90)"/>';
    }
    if (n.ticks > 1) {
      var k = Math.min(n.ticks, 6),
        rt = r + (n.ring != null ? 12 : 7);
      for (var i = 0; i < k; i++) {
        var a = ((-90 + (i - (k - 1) / 2) * 20) * Math.PI) / 180;
        ring +=
          '<circle class="tick" r="2.8" cx="' +
          r1(Math.cos(a) * rt) +
          '" cy="' +
          r1(Math.sin(a) * rt) +
          '"/>';
      }
    }
    var badge = "";
    if (n.badge) {
      var bt = String(n.badge),
        bw = Math.max(17, tw(bt, 11.5) + 8),
        bx = r * 0.72,
        by = -r * 0.78;
      badge =
        '<g class="badge" transform="translate(' +
        r1(bx) +
        "," +
        r1(by) +
        ')"><rect x="' +
        r1(-bw / 2) +
        '" y="-8.5" width="' +
        r1(bw) +
        '" height="17" rx="8.5"/><text text-anchor="middle" y="4">' +
        esc(bt) +
        "</text></g>";
    }
    var pulse = '<circle class="pulse" r="' + r + '"/>';
    var maxw = n.maxw || 220,
      lines;
    if (n.labelLines)
      lines = n.labelLines.map(function (l) {
        return fit(l, maxw, fs);
      });
    else if ((n.labelPos || "below") === "below")
      lines = wrap(n.label, n.wrapAt || 20)
        .slice(0, 2)
        .map(function (l) {
          return fit(l, maxw, fs);
        });
    else lines = [fit(n.label, maxw, fs)];
    if (
      !n.labelLines &&
      (n.labelPos || "below") === "below" &&
      wrap(n.label, n.wrapAt || 20).length > 2
    )
      lines[1] = fit(lines[1] + "…", maxw, fs).replace(/……$/, "…");
    var sub = n.sub ? fit(n.sub, maxw, 12.5) : "";
    var lp = n.labelPos || "below",
      t = "",
      gap = r + (n.ring != null ? 14 : 10) + (n.floor ? 4 : 0);
    if (lp === "left" || lp === "right") {
      var sgn = lp === "left" ? -1 : 1,
        anc = lp === "left" ? ' text-anchor="end"' : "",
        lx = sgn * gap,
        ly = sub ? -2 : 5;
      t =
        '<text class="lab"' +
        anc +
        ' x="' +
        lx +
        '" y="' +
        ly +
        '">' +
        esc(lines.join(" ")) +
        "</text>";
      if (sub)
        t +=
          '<text class="sub"' +
          anc +
          ' x="' +
          lx +
          '" y="' +
          (ly + 17) +
          '">' +
          esc(sub) +
          "</text>";
      t +=
        '<text class="livesub" data-livesub=""' +
        anc +
        ' x="' +
        lx +
        '" y="' +
        (ly + (sub ? 34 : 17)) +
        '"></text>';
    } else {
      var yy = gap + fs + 2;
      lines.forEach(function (l, i) {
        t +=
          '<text class="lab" text-anchor="middle" y="' +
          (yy + i * (fs + 4)) +
          '">' +
          esc(l) +
          "</text>";
      });
      yy += lines.length * (fs + 4) - 2;
      if (sub) {
        t +=
          '<text class="sub" text-anchor="middle" y="' +
          yy +
          '">' +
          esc(sub) +
          "</text>";
        yy += 16;
      }
      t +=
        '<text class="livesub" data-livesub="" text-anchor="middle" y="' +
        yy +
        '"></text>';
      t +=
        '<text class="livechg" data-livechg="" text-anchor="middle" y="' +
        (yy + 16) +
        '"></text>';
    }
    var inner =
      '<g class="' +
      cls +
      '" data-node="' +
      esc(n.id) +
      '" transform="translate(' +
      x +
      "," +
      y +
      ')"' +
      style +
      ">" +
      pulse +
      ring +
      shapePath(n.shape, r) +
      glyphs(r) +
      badge +
      t +
      "</g>";
    var title = "<title>" + esc(n.title || n.label) + "</title>";
    if (n.href)
      return (
        '<a class="nlink" href="' +
        esc(n.href) +
        '" aria-label="' +
        esc(n.title || n.label) +
        '">' +
        title +
        inner +
        "</a>"
      );
    return (
      '<g role="img" aria-label="' +
      esc(n.title || n.label) +
      '">' +
      title +
      inner +
      "</g>"
    );
  }

  // e: {id, d, mid, label: [..], kind, events: [..], dashed}
  function edge(e) {
    var cls =
      "edge k-" +
      (e.kind || "flow") +
      (e.dashed ? " dashed" : "") +
      (e.faded ? " faded" : "") +
      (e.seg ? " seg-" + e.seg : "");
    var lab = "";
    if (e.label && e.label.length) {
      var ls = e.label.slice(0, 3);
      if (e.label.length > 3) ls.push("and " + (e.label.length - 3) + " more");
      var y0 = e.mid.y - (ls.length - 1) * 8 - 4;
      lab = ls
        .map(function (l, i) {
          return (
            '<text class="elab" text-anchor="middle" x="' +
            r1(e.mid.x) +
            '" y="' +
            r1(y0 + i * 16) +
            '">' +
            esc(l) +
            "</text>"
          );
        })
        .join("");
    }
    var ends =
      (e.from ? ' data-from="' + esc(e.from) + '"' : "") +
      (e.to ? ' data-to="' + esc(e.to) + '"' : "");
    var sw = e.weight ? ' style="stroke-width:' + r1(e.weight) + '"' : "";
    return (
      '<g class="' +
      cls +
      '" data-edge="' +
      esc(e.id || "") +
      '"' +
      ends +
      ' data-events="' +
      esc((e.events || []).join(" ")) +
      '">' +
      '<path class="ep" d="' +
      e.d +
      '"' +
      sw +
      ' marker-end="url(#arrow)"/>' +
      lab +
      "</g>"
    );
  }

  function svg(w, h, body, label) {
    w = Math.ceil(w);
    h = Math.ceil(h);
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" class="graph" width="' +
      w +
      '" height="' +
      h +
      '" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="group" aria-label="' +
      esc(label || "graph") +
      '">' +
      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" markerWidth="11" markerHeight="11" orient="auto-start-reverse"><path class="ah" d="M0,0 L10,5 L0,10 z"/></marker></defs>' +
      body +
      '<g class="tokens"></g></svg>'
    );
  }

  // ------------------------------------------------------------------ vertical flow of a workflow tree
  // Returns placed leaves and frames. Leaves sit on a spine; containers draw a frame with a header.
  var ROW = 76,
    R = 18,
    IND = 34,
    HEAD = 46;
  function flow(tree, opt) {
    opt = opt || {};
    var leaves = [],
      frames = [],
      seq = [],
      jumps = [];
    var maxX = 0;
    function leafW(n) {
      return (
        2 * R +
        24 +
        Math.min(300, Math.max(tw(n.name, 14), tw(n.sub || "", 12.5)))
      );
    }
    function place(items, x, y, depth, parentKey) {
      var top = y,
        first = null,
        prevExit = null,
        wmax = 0,
        keys = items.map(function (n) {
          return n.name;
        });
      items.forEach(function (n, i) {
        var box;
        if (
          (n.children || n.branches) &&
          !(opt.collapsed && opt.collapsed[n.key])
        )
          box = container(n, x, y, depth);
        else {
          var cy = y + ROW / 2;
          leaves.push({ n: n, x: x + R, y: cy });
          box = {
            entry: { x: x + R, y: cy - R },
            exit: { x: x + R, y: cy + R },
            h: ROW,
            w: leafW(n),
            anchor: { x: x + R, y: cy },
          };
          maxX = Math.max(maxX, x + box.w);
        }
        box.n = n;
        if (prevExit)
          seq.push({
            from: prevExit,
            to: box.entry,
            a: items[i - 1].key,
            b: n.key,
          });
        prevExit = box.exit;
        if (!first) first = box;
        items[i]._box = box;
        y += box.h;
        wmax = Math.max(wmax, box.w);
      });
      // jumps between siblings (then, switch cases) that are not to the next item
      items.forEach(function (n, i) {
        var targets = [];
        if (n.cases)
          n.cases.forEach(function (c) {
            if (c.then && c.then !== "continue")
              targets.push({
                to: c.then,
                label: c.when_read ? "when " + c.when_read : c.name,
              });
          });
        if (n.then) targets.push({ to: n.then, label: "then " + n.then });
        targets.forEach(function (tg) {
          var j = keys.indexOf(tg.to);
          if (j >= 0 && j !== i + 1)
            jumps.push({
              a: n._box.anchor || n._box.entry,
              b: items[j]._box.anchor || items[j]._box.entry,
              label: tg.label,
              from: n.key,
              to: items[j].key,
            });
        });
      });
      return {
        entry: first ? first.entry : { x: x + R, y: top },
        exit: prevExit || { x: x + R, y: top },
        h: y - top,
        w: wmax,
      };
    }
    function container(n, x, y, depth) {
      var head = n.loop
        ? n.loop.rework
          ? "rework loop, " + n.loop.bound
          : "for each " + n.loop.each + ", " + n.loop.bound
        : n.fork
          ? "fork, " +
            n.branches.length +
            " branches, " +
            (n.fork.compete ? "first to finish wins" : "waits for all")
          : n.label;
      var inner, w;
      if (n.branches) {
        var bx = x + IND,
          hmax = 0,
          bw = 0,
          bs = [];
        n.branches.forEach(function (b) {
          var r = place(b, bx, y + HEAD, depth + 1, n.key);
          bs.push(r);
          hmax = Math.max(hmax, r.h);
          bx += Math.max(r.w, 200) + 40;
          bw = bx - x;
        });
        inner = {
          h: hmax,
          entry: bs[0] ? bs[0].entry : { x: x + IND, y: y + HEAD },
          exit: { x: x + R, y: y + HEAD + hmax + 16 },
        };
        w = bw;
        bs.forEach(function (r, k) {
          seq.push({
            from: { x: x + R, y: y + HEAD - 14 },
            to: r.entry,
            a: n.key,
            b: n.branches[k][0] ? n.branches[k][0].key : null,
            fork: true,
          });
        });
      } else {
        inner = place(n.children, x + IND, y + HEAD, depth + 1, n.key);
        w = inner.w + IND + 30;
      }
      var h = HEAD + inner.h + 18;
      w = Math.max(w, tw(n.name + "  " + head, 14) + 40);
      frames.push({
        n: n,
        x: x,
        y: y + 4,
        w: w,
        h: h - 8,
        head: head,
        rework: n.loop && n.loop.rework,
        depth: depth,
      });
      maxX = Math.max(maxX, x + w);
      if (!n.branches)
        seq.push({
          from: { x: x + R, y: y + HEAD - 14 },
          to: inner.entry,
          a: n.key,
          b: n.children[0] ? n.children[0].key : null,
          inner: true,
        });
      return {
        entry: { x: x + R, y: y + 8 },
        exit: { x: x + R, y: y + h - 4 },
        h: h,
        w: w,
        anchor: { x: x + R, y: y + 24 },
      };
    }
    var top = place(tree, opt.x || 40, opt.y || 30, 0, "");
    var jx = maxX + 30;
    jumps.forEach(function (j, i) {
      j.x = jx + i * 18;
    });
    var labelW = 0;
    jumps.forEach(function (j) {
      labelW = Math.max(labelW, tw(j.label, 13));
    });
    return {
      leaves: leaves,
      frames: frames,
      seq: seq,
      jumps: jumps,
      w: jx + jumps.length * 18 + (jumps.length ? labelW + 30 : 20),
      h: (opt.y || 30) + top.h + 30,
      entry: top.entry,
      R: R,
    };
  }

  var api = {
    esc: esc,
    tw: tw,
    wrap: wrap,
    fit: fit,
    layered: layered,
    edgePath: edgePath,
    node: node,
    edge: edge,
    svg: svg,
    flow: flow,
    STATES: STATES,
    r1: r1,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.G = api;
})(this);
