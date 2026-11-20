/* Views: route -> HTML string, live state per node, feedback per ledger event. Pure: no DOM. */
(function (root) {
  "use strict";
  var G =
    root.G || (typeof require !== "undefined" ? require("./graph.js") : null);
  var esc = G.esc;

  // ------------------------------------------------------------------ routes
  function enc(s) {
    return encodeURIComponent(s);
  }
  function parse(hash) {
    var h = String(hash || "").replace(/^#/, "");
    if (h === "" || h === "/") return { view: "home" };
    var p = h
      .replace(/^\//, "")
      .split("/")
      .map(function (x) {
        try {
          return decodeURIComponent(x);
        } catch (e) {
          return x;
        }
      });
    var r = { view: "notfound", raw: h };
    if (p[0] === "s" && p[1]) r = { view: "segment", seg: p[1] };
    else if (p[0] === "w" && p[1]) {
      r = { view: "workflow", wf: p[1], ops: false, run: null, sel: null };
      var i = 2;
      if (p[i] === "r" && p[i + 1]) {
        r.run = p[i + 1];
        i += 2;
      }
      if (p[i] === "ops") {
        r.ops = true;
        i += 1;
      }
      if (p[i] === "n" && p.length > i + 1) r.sel = p.slice(i + 1).join("/");
      else if (p.length > i) r = { view: "notfound", raw: h };
    } else if (p[0] === "c" && p[1])
      r = {
        view: "component",
        id: p[1],
        sel: p[2] === "u" ? p[3] || null : null,
      };
    else if (p[0] === "build") r = { view: "build", sel: p[1] || null };
    else if (p[0] === "language") r = { view: "language", sel: p[1] || null };
    else if (p[0] === "decisions") r = { view: "decisions", sel: p[1] || null };
    if (p.length > 2 && r.view === "segment") r = { view: "notfound", raw: h };
    return r;
  }
  function wfHref(wf, o) {
    o = o || {};
    var h = "#/w/" + enc(wf);
    if (o.run) h += "/r/" + enc(o.run);
    if (o.ops) h += "/ops";
    if (o.sel) h += "/n/" + enc(o.sel);
    return h;
  }
  function itemHref(D, id) {
    var it = D.org.items[id];
    return it && it.kind === "component" ? "#/c/" + enc(id) : wfHref(id);
  }

  // ------------------------------------------------------------------ helpers
  var ST = {
    done: "built, nothing open",
    active: "being built",
    gate: "waits for you",
    failed: "a unit failed",
  };
  function dur(s) {
    s = Math.max(0, Math.round(s));
    if (s < 60) return s + " s";
    if (s < 3600) return Math.floor(s / 60) + " min " + (s % 60) + " s";
    return Math.floor(s / 3600) + " h " + Math.floor((s % 3600) / 60) + " min";
  }
  function ago(ts, now) {
    return ts ? dur(now - ts) + " ago" : "unknown";
  }
  function usd(x) {
    return x >= 0.01
      ? x.toFixed(2) + " USD"
      : x > 0
        ? x.toFixed(4) + " USD"
        : "0 USD";
  }
  // Breadcrumb as a path: one pip per level, colored by the level's segment; the current level is filled.
  // list: [[label, href, segId?, mono?]]
  function crumbs(list) {
    return (
      '<nav aria-label="Breadcrumbs"><ol class="crumbs">' +
      list
        .map(function (c, i) {
          var lab =
            '<span class="pip" aria-hidden="true"></span>' +
            (c[3] ? '<span class="id">' + esc(c[0]) + "</span>" : esc(c[0]));
          return (
            "<li" +
            (c[2] ? ' class="seg-' + esc(c[2]) + '"' : "") +
            ">" +
            (i === list.length - 1
              ? '<span aria-current="page">' + lab + "</span>"
              : '<a href="' + c[1] + '">' + lab + "</a>") +
            "</li>"
          );
        })
        .join("") +
      "</ol></nav>"
    );
  }
  function goalBox(text, label) {
    return text
      ? '<div class="goal"><b>' +
          esc(label || "Goal") +
          "</b><p>" +
          esc(text) +
          "</p></div>"
      : "";
  }
  // o: {goal, seg, mono}
  function head(cr, title, lead, extra, o) {
    o = o || {};
    return (
      '<header class="vh' +
      (o.seg ? " seg-" + esc(o.seg) : "") +
      '">' +
      crumbs(cr) +
      '<h1 tabindex="-1">' +
      (o.mono ? '<span class="id">' + esc(title) + "</span>" : esc(title)) +
      "</h1>" +
      (lead ? '<p class="lead">' + lead + "</p>" : "") +
      goalBox(o.goal) +
      (extra || "") +
      "</header>"
    );
  }
  function stage(svgHtml, panelHtml, cap, leg, seg) {
    return (
      '<div class="stage' +
      (panelHtml ? " has-panel" : "") +
      '"><figure class="canvas' +
      (seg ? " seg-" + esc(seg) : "") +
      '"><div class="sb">' +
      svgHtml +
      "</div>" +
      (cap || leg
        ? '<div class="bar">' +
          (leg || "") +
          (cap ? "<figcaption>" + cap + "</figcaption>" : "") +
          "</div>"
        : "") +
      "</figure>" +
      (panelHtml
        ? '<aside class="panel' +
          (seg ? " seg-" + esc(seg) : "") +
          '" aria-label="Detail" aria-live="polite">' +
          panelHtml +
          "</aside>"
        : "") +
      "</div>"
    );
  }
  function chip(st, text) {
    return '<span class="chip st-' + esc(st) + '">' + esc(text) + "</span>";
  }
  // The one panel layout: title, kind and state, then the goal, then the fixed sections in this order.
  // secs: {what, inputs, outputs, checks, history, extra}; an empty section is left out.
  function panel(o) {
    var names = [
      ["what", "What it is"],
      ["inputs", "Inputs"],
      ["outputs", "Outputs"],
      ["checks", "Checks"],
      ["history", "History"],
    ];
    var h =
      '<div class="ph"><div><h2>' +
      (o.mono ? '<span class="id">' + esc(o.title) + "</span>" : esc(o.title)) +
      "</h2>" +
      '<p class="kind">' +
      esc(o.kind || "") +
      (o.st ? " " + chip(o.st[0], o.st[1]) : "") +
      "</p></div>" +
      '<a class="close" href="' +
      o.close +
      '" aria-label="Close the detail">Close</a></div>' +
      goalBox(o.goal || "No goal is written for this yet.");
    names.forEach(function (n) {
      var b = o.secs[n[0]];
      if (b)
        h += '<section class="psec"><h3>' + n[1] + "</h3>" + b + "</section>";
    });
    return h + (o.secs.extra || "");
  }
  function dl(rows) {
    var r = rows.filter(function (r) {
      return r && r[1] != null && r[1] !== "";
    });
    return r.length
      ? "<dl>" +
          r
            .map(function (r) {
              return "<dt>" + esc(r[0]) + "</dt><dd>" + r[1] + "</dd>";
            })
            .join("") +
          "</dl>"
      : "";
  }
  function kv(items) {
    var it = items.filter(function (x) {
      return x && x[1] != null && x[1] !== "";
    });
    return it.length
      ? '<div class="kv">' +
          it
            .map(function (x) {
              return (
                "<div><b" +
                (x[2] != null ? ' data-count="' + x[2] + '"' : "") +
                ">" +
                esc(x[1]) +
                "</b><span>" +
                esc(x[0]) +
                "</span></div>"
              );
            })
            .join("") +
          "</div>"
      : "";
  }
  function code(s) {
    return "<code>" + esc(s) + "</code>";
  }
  function walk(tree, out) {
    out = out || [];
    (tree || []).forEach(function (n) {
      out.push(n);
      walk(n.children, out);
      (n.branches || []).forEach(function (b) {
        walk(b, out);
      });
    });
    return out;
  }
  // Legend: every entry is a filter button; data-filter is a class a graph node carries (st-done, k-check).
  function legend(items) {
    return (
      '<ul class="legend" aria-label="Legend; select an entry to show only those nodes">' +
      items
        .map(function (it) {
          var f = it[3] || "st-" + it[0];
          return (
            '<li><button type="button" data-filter="' +
            esc(f) +
            '" aria-pressed="false"><svg width="26" height="26" viewBox="-13 -13 26 26" aria-hidden="true">' +
            G.node({
              id: "lg",
              x: 0,
              y: 0,
              r: 9,
              st: it[0],
              label: "",
              shape: it[2],
              kind: it[4],
            }).replace(/<title>.*?<\/title>/, "") +
            "</svg>" +
            esc(it[1]) +
            "</button></li>"
          );
        })
        .join("") +
      "</ul>"
    );
  }
  var LEG_STATE = [
    ["done", "done"],
    ["active", "running or building"],
    ["gate", "needs you"],
    ["queued", "queued"],
    ["failed", "failed"],
  ];
  var LEG_RUN = LEG_STATE.concat([
    ["skipped", "skipped"],
    ["escalated", "escalated"],
  ]);
  var LEG_KIND = [
    ["model", "step by a model", null, "by-model", "step"],
    ["code", "step by code", "square", "by-code", "step"],
    ["code", "calls a workflow", null, "k-call", "call"],
    ["human", "you decide (gate)", "hex", "k-gate", "gate"],
    ["event", "event", "tag", "k-event", "event"],
    ["escalated", "escalation", null, "k-raise", "raise"],
  ];
  var LEG_OPS = [
    ["check", "check", "square", "k-check", "check"],
    ["rubric", "rubric a role judges", "diamond", "k-rubric", "rubric"],
    ["human", "your decision", "hex", "k-gate", "gate"],
    ["event", "event in or out", "tag", "k-event", "event"],
    ["role", "judge or caller", null, "k-role", "role"],
  ];
  // a sparkline of values; fewer than two points gives text, never a path built from nothing
  function spark(vals, sts, w, h, label) {
    vals = vals.filter(function (v) {
      return typeof v === "number" && isFinite(v);
    });
    if (vals.length < 2)
      return (
        '<p class="muted">' +
        (vals.length ? "One workflow has run." : "No runs yet.") +
        "</p>"
      );
    var max = Math.max.apply(null, vals) || 1,
      n = vals.length,
      pts = vals.map(function (v, i) {
        return [
          G.r1(4 + (i * (w - 8)) / (n - 1)),
          G.r1(h - 4 - (v / max) * (h - 10)),
        ];
      });
    var line =
      "M" +
      pts
        .map(function (p) {
          return p.join(",");
        })
        .join(" L");
    return (
      '<svg class="spark" width="' +
      w +
      '" height="' +
      h +
      '" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="' +
      esc(label) +
      '">' +
      '<path class="sa" d="' +
      line +
      " L" +
      pts[n - 1][0] +
      "," +
      h +
      " L" +
      pts[0][0] +
      "," +
      h +
      ' Z"/><path class="sl" d="' +
      line +
      '"/>' +
      pts
        .map(function (p, i) {
          return (
            '<circle class="sd st-' +
            esc(sts[i] || "done") +
            '" r="3.5" cx="' +
            p[0] +
            '" cy="' +
            p[1] +
            '"/>'
          );
        })
        .join("") +
      "</svg>"
    );
  }
  function ringStat(done, total, label) {
    var pct = total ? Math.round((done / total) * 100) : 0,
      r = 30,
      c = 2 * Math.PI * r;
    return (
      '<div class="ringstat" role="img" aria-label="' +
      esc(label) +
      '"><svg width="76" height="76" viewBox="-38 -38 76 76"><circle class="rtrack" r="' +
      r +
      '"/>' +
      '<circle class="rprog" r="' +
      r +
      '" transform="rotate(-90)" stroke-dasharray="' +
      G.r1((c * pct) / 100) +
      " " +
      G.r1(c) +
      '" data-ring="' +
      G.r1((c * pct) / 100) +
      '"/></svg><b data-count="' +
      pct +
      '" data-suffix="%">' +
      pct +
      "%</b></div>"
    );
  }

  // ------------------------------------------------------------------ live helpers
  // The latest-state projection: every count, list and graph reads runs(D), the newest run of each workflow
  // (a running one first, then the latest start). Older runs stay in the ledgers; only a run's own panel lists them.
  function allRuns(D) {
    return (D.live && D.live.runs) || [];
  }
  function newer(a, b) {
    return (
      (a.status === "running") - (b.status === "running") ||
      (a.started || 0) - (b.started || 0) ||
      (a.last || 0) - (b.last || 0)
    );
  }
  function runs(D) {
    var best = {};
    allRuns(D).forEach(function (r) {
      var k = r.workflow || r.id;
      if (!best[k] || newer(r, best[k]) > 0) best[k] = r;
    });
    return Object.keys(best)
      .map(function (k) {
        return best[k];
      })
      .sort(function (a, b) {
        return (b.last || 0) - (a.last || 0);
      });
  }
  function running(D) {
    return runs(D).filter(function (r) {
      return r.status === "running";
    });
  }
  function touches(r, wf) {
    return (r.workflows || []).indexOf(wf) >= 0 || r.workflow === wf;
  }
  function runsOf(D, wf) {
    return runs(D).filter(function (r) {
      return touches(r, wf);
    });
  }
  function olderRuns(D, run) {
    return allRuns(D)
      .filter(function (r) {
        return r.workflow === run.workflow && r.id !== run.id;
      })
      .sort(function (a, b) {
        return newer(b, a);
      });
  }
  function pickRun(D, wf, id) {
    if (id)
      return (
        allRuns(D).filter(function (r) {
          return r.id === id && touches(r, wf);
        })[0] || null
      ); // an old run stays reachable by its link
    return (
      runsOf(D, wf).filter(function (r) {
        return r.status === "running";
      })[0] || null
    );
  }
  function segOf(D, wf) {
    var it = D.org.items[wf];
    return it ? it.seg : null;
  }
  function stepLine(r, now) {
    var c = (r.current || [])[0];
    if (!c) return r.status === "running" ? "starting" : "";
    var idle = r.idle != null && r.last ? now - r.last : 0;
    return (
      c.rel +
      " " +
      dur(now - c.since) +
      ", " +
      usd(r.cost_usd) +
      (idle > 900 ? ", no ledger entry for " + dur(idle) : "")
    );
  }
  function changeLine(r) {
    var c = r && r.change;
    if (!c) return "";
    if (!c.files) return "changed files unknown";
    var n = c.files.length;
    if (!n) return "";
    var hi = c.rungs && c.rungs.highest;
    return (
      n +
      " file" +
      (n === 1 ? "" : "s") +
      " changed" +
      (hi ? ", highest rung " + hi : "")
    );
  }
  function taskState(t, node) {
    if (!t) return "queued";
    if (t.state === "running")
      return node && node.kind === "gate" ? "gate" : "active";
    return (
      {
        done: "done",
        failed: "failed",
        skipped: "skipped",
        escalated: "escalated",
        interrupted: "interrupted",
      }[t.state] || "queued"
    );
  }
  function designState(n) {
    if (n.kind === "gate" || n.by === "human") return "human";
    if (n.by === "code" || n.kind === "call" || n.kind === "switch")
      return "code";
    if (n.kind === "emit" || n.kind === "listen" || n.kind === "wait")
      return "event";
    return "model";
  }
  function tasksFor(r, wf) {
    var out = {};
    if (!r) return out;
    Object.keys(r.tasks || {}).forEach(function (k) {
      var t = r.tasks[k];
      if (t.wf === wf) out[t.rel] = t;
    });
    return out;
  }

  // ------------------------------------------------------------------ derived numbers (magnitude encodings)
  function segOfUnit(D, u) {
    for (var i = 0; i < u.items.length; i++) {
      var it = D.org.items[u.items[i]];
      if (it) return it.seg;
    }
    return "platform";
  }
  function unitsOfSeg(D, sid) {
    return D.build.units.filter(function (u) {
      return (
        u.items.some(function (i) {
          return D.org.items[i] && D.org.items[i].seg === sid;
        }) ||
        (sid === "platform" && !u.items.length)
      );
    });
  }
  function doneFrac(us) {
    return us.length
      ? us.filter(function (u) {
          return u.st === "done";
        }).length / us.length
      : null;
  }
  function leavesOf(w) {
    return walk(w.tree).filter(function (n) {
      return !n.children && !n.branches;
    });
  }
  function wfStats(D, id) {
    var w = D.workflows[id],
      rs = runsOf(D, id);
    if (!w) return { steps: 0, checks: 0, runs: rs.length, usd: 0 };
    var ls = leavesOf(w),
      ch = 0;
    ls.forEach(function (n) {
      ch += (n.acceptance || []).length;
    });
    return {
      steps: ls.length,
      checks: ch,
      runs: rs.length,
      usd: rs.reduce(function (a, r) {
        return a + (r.cost_usd || 0);
      }, 0),
    };
  }
  function runSt(r) {
    return r.status === "running"
      ? "active"
      : r.end_status === "success"
        ? "done"
        : "failed";
  }

  // ------------------------------------------------------------------ goals: what a thing is for, at every level
  function strip(h) {
    return String(h || "")
      .replace(/<[^>]+>/g, "")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/\s+/g, " ")
      .trim();
  }
  function briefGoal(n) {
    if (!n.brief || !n.brief.html) return "";
    var h = n.brief.html.split(/<h5/)[0],
      t = (h.match(/<h4[^>]*>([\s\S]*?)<\/h4>/) || [])[1],
      ps = [];
    h.replace(/<p>([\s\S]*?)<\/p>/g, function (_, p) {
      ps.push(strip(p));
      return "";
    });
    var p = ps.filter(function (x) {
      return x && !/^Role:/.test(x);
    })[0];
    t = t ? strip(t) : "";
    return t && p ? t + ". " + p : t || p || "";
  }
  function kids(n) {
    var names = (n.children || []).map(function (c) {
      return c.name;
    });
    return names.length > 4
      ? names.slice(0, 4).join(", ") + " and " + (names.length - 4) + " more"
      : names.join(", ");
  }
  function stepGoal(n) {
    var b = briefGoal(n);
    if (b) return b;
    var acc = n.acceptance || [],
      checks = acc
        .filter(function (a) {
          return a.type === "check";
        })
        .map(function (a) {
          return a.id;
        });
    if (n.kind === "call" && n.call)
      return "Runs the workflow " + n.call.name + " on " + n.call.input + ".";
    if (n.kind === "gate") {
      var hs = acc
        .filter(function (a) {
          return a.type === "human";
        })
        .map(function (a) {
          return a.text;
        });
      return (
        "You decide" +
        (hs.length ? ": " + hs.join("; ") : " before the flow goes on") +
        "."
      );
    }
    if (n.kind === "raise" && n.raise)
      return (
        "Escalates to " +
        (n.raise.to || "the next role") +
        ": " +
        n.raise.title +
        "."
      );
    if (n.kind === "emit" && n.emits)
      return (
        "Emits " +
        n.emits.type +
        (n.emits.starts.length
          ? ", which starts " + n.emits.starts.join(", ")
          : "; no workflow listens yet") +
        "."
      );
    if (n.kind === "listen" && n.listens)
      return "Waits for " + n.listens.type + ".";
    if (n.kind === "switch" && n.cases)
      return (
        "Chooses the next step: " +
        n.cases
          .map(function (c) {
            return c.name;
          })
          .join(", ") +
        "."
      );
    if (n.loop)
      return (
        (n.loop.rework
          ? "Repeats " + kids(n) + " until accepted, "
          : "For each " + n.loop.each + ", runs " + kids(n) + ", ") +
        n.loop.bound +
        "."
      );
    if (n.branches)
      return (
        "Runs " +
        n.branches.length +
        " branches at once, " +
        (n.fork && n.fork.compete
          ? "and the first to finish wins"
          : "and waits for all") +
        "."
      );
    if (n.children) return "Groups " + kids(n) + ".";
    if (checks.length)
      return (
        "A code step" +
        (n.command ? " that runs " + n.command : "") +
        "; its result must pass " +
        checks.join(", ") +
        "."
      );
    return n.command ? "Runs " + n.command + "." : "";
  }
  // level: segment | workflow | component | unit | step
  function goal(D, level, x) {
    if (!x) return "";
    if (level === "segment") return x.about || "";
    if (level === "workflow") return x.summary || x.title || "";
    if (level === "component") return x.summary || "";
    if (level === "unit") return x.what || x.tgt || "";
    return stepGoal(x);
  }

  // ------------------------------------------------------------------ home
  // The three lists of the critical band; the sidebar counts the same lists.
  function critical(D, now) {
    var C = D.org.critical,
      act = running(D);
    var building = act
      .filter(function (r) {
        return !waitsForOwner(D, r);
      })
      .map(function (r) {
        return (
          '<li><a href="' +
          wfHref(r.workflow, { run: r.id }) +
          '">' +
          esc(r.workflow) +
          "</a> " +
          esc(stepLine(r, now)) +
          "</li>"
        );
      })
      .concat(C.building.map(unitLi));
    var owner = act
      .filter(function (r) {
        return waitsForOwner(D, r);
      })
      .map(function (r) {
        return (
          '<li><a href="' +
          wfHref(r.workflow, { run: r.id }) +
          '">' +
          esc(r.workflow) +
          " waits for your decision</a> " +
          esc(stepLine(r, now)) +
          "</li>"
        );
      })
      .concat(
        C.needs_owner.map(function (id) {
          var d = D.decisions.items.filter(function (x) {
            return x.id === id;
          })[0];
          return d
            ? '<li><a href="#/decisions/' +
                enc(id) +
                '">' +
                esc(d.title) +
                "</a></li>"
            : "";
        }),
      )
      .concat((C.owner_units || []).map(unitLi));
    var failing = (
      C.gh_error
        ? ['<li class="warn">Unknown: gh failed (' + esc(C.gh_error) + ")</li>"]
        : C.failing.map(function (p) {
            return "<li>Pull request #" + p.n + " " + esc(p.title) + "</li>";
          })
    )
      .concat((C.failing_units || []).map(unitLi))
      .concat(
        runs(D)
          .filter(function (r) {
            return (
              r.status !== "running" &&
              r.end_status &&
              r.end_status !== "success"
            );
          })
          .map(function (r) {
            return (
              '<li><a href="' +
              wfHref(r.workflow, { run: r.id }) +
              '">Latest run of ' +
              esc(r.workflow) +
              "</a> ended with " +
              esc(r.end_status) +
              ", " +
              esc(ago(r.last, now)) +
              "</li>"
            );
          }),
      );
    return {
      building: building,
      owner: owner,
      failing: failing,
      unknown: !!C.gh_error,
    };
  }
  function clip(t, n) {
    t = String(t || "");
    return t.length > n ? t.slice(0, n - 1).replace(/\W*\S*$/, "") + "…" : t;
  }
  function noteOf(st, note) {
    return note && note !== st && note.indexOf(st) !== 0 ? note : "";
  }
  function unitLi(b) {
    var n = noteOf(b.state, b.note);
    return (
      '<li><a href="#/build/' +
      enc(b.unit) +
      '">' +
      esc(b.unit + " " + b.name) +
      "</a> " +
      esc((b.state || "") + (n ? (b.state ? ", " : "") + clip(n, 48) : "")) +
      "</li>"
    );
  }
  function waitsForOwner(D, r) {
    return (r.current || []).some(function (c) {
      return isGate(D, c.wf, c.rel);
    });
  }
  function runRow(D, r, now) {
    return (
      '<li><svg width="22" height="22" viewBox="-11 -11 22 22" aria-hidden="true">' +
      G.node({ id: "x", x: 0, y: 0, r: 8, st: runSt(r), label: "" }).replace(
        /<title>.*?<\/title>/,
        "",
      ) +
      "</svg>" +
      '<a href="' +
      wfHref(r.workflow, { run: r.id }) +
      '"><span class="id">' +
      esc(r.workflow) +
      "</span>" +
      (r.title ? ": " + esc(r.title) : "") +
      "</a>" +
      '<span class="cost">' +
      esc(costTxt(r)) +
      "</span>" +
      '<span class="meta">' +
      esc(
        r.status === "running"
          ? "running, " + stepLine(r, now)
          : "ended " + (r.end_status || "") + ", " + ago(r.last, now),
      ) +
      ", " +
      (r.calls || 0) +
      " step calls</span></li>"
    );
  }
  function costTxt(r) {
    return usd(r.cost_usd || 0) + (r.cost_partial ? ", partial" : "");
  }
  function home(D, opt) {
    var now = opt.now,
      K = critical(D, now),
      t = D.org.totals;
    function slot(cls, title, list, empty) {
      return (
        '<section class="slot ' +
        cls +
        (list.length ? " on" : "") +
        '"><h2>' +
        esc(title) +
        ' <span data-count="' +
        list.length +
        '" class="n">' +
        list.length +
        "</span></h2>" +
        (list.length
          ? "<ul>" + list.join("") + "</ul>"
          : '<p class="empty">' + esc(empty) + "</p>") +
        "</section>"
      );
    }
    var rs = runs(D)
      .slice()
      .sort(function (a, b) {
        return (a.started || 0) - (b.started || 0);
      });
    var total = rs.reduce(function (a, r) {
        return a + (r.cost_usd || 0);
      }, 0),
      partial = rs.some(function (r) {
        return r.cost_partial;
      });
    var calls = rs.reduce(function (a, r) {
      return a + (r.model_calls != null ? r.model_calls : 0);
    }, 0);
    var pulse =
      '<section class="slot pulse-slot"><h2>Build and runs</h2>' +
      ringStat(
        t.done,
        t.units,
        t.done + " of " + t.units + " build units done",
      ) +
      '<div class="sparkbox"><p><a href="#/build"><b data-count="' +
      t.done +
      '" class="num">' +
      t.done +
      "</b> of " +
      t.units +
      " units done</a></p>" +
      spark(
        rs.map(function (r) {
          return r.cost_usd || 0;
        }),
        rs.map(runSt),
        160,
        34,
        "Cost of the latest run of each workflow, oldest first",
      ) +
      "<p>Latest run" +
      (rs.length === 1 ? "" : "s") +
      " of " +
      rs.length +
      " workflow" +
      (rs.length === 1 ? "" : "s") +
      (calls ? ", " + calls + " model calls" : "") +
      ", " +
      esc(usd(total)) +
      (partial ? ', <span class="warn">cost partial</span>' : "") +
      "</p></div></section>";
    var band =
      '<div class="band" role="region" aria-label="What needs attention">' +
      slot(
        "s-build",
        "Building now",
        K.building,
        "Nothing is running or being built.",
      ) +
      slot("s-owner", "Needs you", K.owner, "Nothing waits for you.") +
      slot("s-fail", "Failing", K.failing, "No failing checks or runs.") +
      pulse +
      "</div>";
    var segs = D.org.segments
      .map(function (s) {
        var us = unitsOfSeg(D, s.id),
          f = doneFrac(us),
          pct = f == null ? 0 : Math.round(f * 100);
        return (
          '<li class="seg-' +
          esc(s.id) +
          '"><span class="sw" aria-hidden="true"></span><span><a href="#/s/' +
          enc(s.id) +
          '">' +
          esc(s.name) +
          "</a> " +
          chip(s.st, ST[s.st] || s.st) +
          '<br><span class="muted num">' +
          s.items.length +
          (s.id === "platform" ? " components" : " workflows") +
          ", " +
          us.length +
          " build units</span></span>" +
          '<span class="meter" role="img" aria-label="' +
          pct +
          ' percent of its units done"><i style="width:' +
          pct +
          '%"></i></span></li>'
        );
      })
      .join("");
    var recent = runs(D)
      .slice(0, 8)
      .map(function (r) {
        return runRow(D, r, now);
      })
      .join("");
    return (
      head(
        [["Organization", "#/"]],
        "Organization",
        "Four segments, each a set of workflows. Select a segment to go in, or press / to jump anywhere.",
      ) +
      band +
      stage(
        orgGraph(D, opt),
        null,
        "Arrow width grows with the number of calls and events between two segments; dashed arrows are flows no file states yet. A ring shows the share of build units done.",
        legend(LEG_STATE),
      ) +
      '<div class="groups"><details class="group" open><summary>Segments <span class="n">' +
      D.org.segments.length +
      '</span></summary><ul class="segs">' +
      segs +
      "</ul></details>" +
      '<details class="group" open><summary>Latest run per workflow <span class="n">' +
      runs(D).length +
      "</span></summary>" +
      (recent
        ? '<ul class="runs">' + recent + "</ul>"
        : '<p class="empty">No runtime ledger found. Name ledgers or state directories in <code>site/live-sources.json</code>.</p>') +
      '<p class="note">From the runtime ledgers: ' +
      esc(D.live.verified || "") +
      ". Earlier runs are listed in each run's own box.</p></details>" +
      metricsGroup(D) +
      "</div>" +
      (opt.width && opt.width < 760
        ? '<p class="note">' + orgEdgeText(D) + "</p>"
        : "")
    );
  }
  // latest value of each org metric, from the last org.metric ledger entry (live.py org_metric); none: no collector
  function metricLatest(D, id) {
    var m = D.live && D.live.metrics && D.live.metrics[id];
    return m || null;
  }
  function metricTxt(D, id) {
    var m = metricLatest(D, id);
    return m
      ? String(m.value) + (m.reason ? ", " + m.reason : "")
      : "no collector";
  }
  function metricsGroup(D) {
    var ids = [],
      by = {};
    Object.keys(D.workflows).forEach(function (w) {
      D.workflows[w].metrics.forEach(function (m) {
        if (!by[m.id]) {
          by[m.id] = m;
          ids.push(m.id);
        }
      });
    });
    Object.keys((D.live && D.live.metrics) || {}).forEach(function (id) {
      if (!by[id]) {
        by[id] = { id: id };
        ids.push(id);
      }
    });
    if (!ids.length) return "";
    var have = ids.filter(function (id) {
      return metricLatest(D, id);
    }).length;
    return (
      '<details class="group"><summary>Metrics, latest value <span class="n">' +
      have +
      " of " +
      ids.length +
      '</span></summary><ul class="plain">' +
      ids
        .sort()
        .map(function (id) {
          var m = by[id];
          return (
            "<li>" +
            code(id) +
            " " +
            (metricLatest(D, id)
              ? "<b>" + esc(metricTxt(D, id)) + "</b>"
              : '<span class="muted">no collector</span>') +
            (m.target ? ", target " + esc(m.target) : "") +
            "</li>"
          );
        })
        .join("") +
      "</ul></details>"
    );
  }
  function orgEdgeText(D) {
    return D.org.edges
      .map(function (e) {
        return (
          (e.from === "owner" ? "You" : segName(D, e.from)) +
          " to " +
          segName(D, e.to) +
          ": " +
          e.label.join(", ") +
          "."
        );
      })
      .map(esc)
      .join(" ");
  }
  function isGate(D, wf, rel) {
    var w = D.workflows[wf];
    if (!w) return false;
    return walk(w.tree).some(function (n) {
      return n.key === rel && n.kind === "gate";
    });
  }

  function orgGraph(D, opt) {
    var segs = D.org.segments,
      narrow = opt.width && opt.width < 760;
    var dir = narrow ? "TB" : "LR",
      avail = (opt.width || 1200) - 60;
    var flowSegs = segs.filter(function (s) {
      return s.id !== "platform";
    });
    var nodes = [{ id: "owner", layer: 0 }].concat(
      flowSegs.map(function (s) {
        return { id: s.id };
      }),
    );
    var edges = D.org.edges.filter(function (e) {
      return e.to !== "platform" && e.from !== "platform";
    });
    var gm = narrow ? 170 : Math.max(230, Math.min(360, (avail - 420) / 2));
    var lay = G.layered(
      nodes,
      edges.filter(function (e) {
        return !e.inferred;
      }),
      {
        dir: dir,
        gapMain: gm,
        gapCross: narrow ? 175 : 220,
        pad: narrow ? 84 : 96,
      },
    );
    var P = lay.pos,
      body = "",
      w = narrow
        ? lay.w + 40
        : Math.min(Math.max(lay.w + 150, 700), Math.max(avail, lay.w + 60)),
      h = lay.h + 40;
    var maxRuns = 1;
    flowSegs.forEach(function (s) {
      maxRuns = Math.max(maxRuns, segRuns(s));
    });
    function segRuns(s) {
      return s.items.reduce(function (a, i) {
        return a + runsOf(D, i).length;
      }, 0);
    }
    function radius(s) {
      return Math.round(24 + 5 * Math.sqrt(s.items.length));
    }
    flowSegs.forEach(function (s) {
      body +=
        '<circle class="terr seg-' +
        esc(s.id) +
        '" cx="' +
        P[s.id].x +
        '" cy="' +
        P[s.id].y +
        '" r="' +
        (radius(s) + 34) +
        '"/>';
    });
    var pairCount = {};
    edges.forEach(function (e) {
      var k = [e.from, e.to].sort().join("|");
      pairCount[k] = (pairCount[k] || 0) + 1;
      var bend = pairCount[k] > 1 ? 18 : 0;
      var ra =
        e.from === "owner"
          ? 30
          : radius(
              segs.filter(function (s) {
                return s.id === e.from;
              })[0] || { items: [] },
            ) + 6;
      var rb =
        radius(
          segs.filter(function (s) {
            return s.id === e.to;
          })[0] || { items: [] },
        ) + 6;
      var p = G.edgePath(P[e.from], P[e.to], dir, ra, rb, bend);
      body += G.edge({
        id: e.from + ">" + e.to,
        from: e.from,
        to: e.to,
        d: p.d,
        mid: p.mid,
        label: narrow ? [] : e.label,
        kind: e.kind,
        dashed: e.inferred,
        events: e.events || e.label,
        seg: e.from === "owner" ? e.to : e.from,
        weight: 1.6 + Math.min(4, (e.label || []).length * 0.8),
      });
    });
    var railY = h + 30;
    var pf = segs.filter(function (s) {
      return s.id === "platform";
    })[0];
    var pfr = doneFrac(unitsOfSeg(D, "platform"));
    body +=
      '<a class="rail-link" href="#/s/platform"><title>Platform: ' +
      esc(ST[pf.st]) +
      '</title><rect class="rail" x="30" y="' +
      (railY - 28) +
      '" width="' +
      (w - 60) +
      '" height="56" rx="28"/>' +
      '<text class="sub" x="' +
      108 +
      '" y="' +
      (railY + 56) +
      '">' +
      (narrow
        ? "Runs every workflow above"
        : "Validators, interpreter, runtime, dispatcher, harness and command line run every workflow above") +
      "</text></a>";
    body += G.node({
      id: "platform",
      x: 62,
      y: railY,
      r: 22,
      lv: 1,
      seg: "platform",
      st: pf.st,
      label: "Platform",
      labelPos: "right",
      href: "#/s/platform",
      title: "Platform: " + ST[pf.st],
      sub: ST[pf.st],
      ring: pfr,
      heat: 0.3,
    });
    body += G.node({
      id: "owner",
      x: P.owner.x,
      y: P.owner.y,
      r: 30,
      lv: 1,
      st: "role",
      label: "You",
      sub: "the owner",
      title: "You, the owner",
    });
    flowSegs.forEach(function (s) {
      var f = doneFrac(unitsOfSeg(D, s.id)),
        n = segRuns(s);
      body += G.node({
        id: s.id,
        x: P[s.id].x,
        y: P[s.id].y,
        r: radius(s),
        lv: 1,
        seg: s.id,
        st: s.st,
        label: s.name,
        sub:
          s.items.length +
          " workflow" +
          (s.items.length === 1 ? "" : "s") +
          (n ? ", " + n + " run" + (n === 1 ? "" : "s") : ""),
        href: "#/s/" + enc(s.id),
        title: s.name + ": " + ST[s.st] + ". " + s.about,
        ring: f,
        heat: 0.14 + (0.3 * n) / maxRuns,
        badge: n || null,
        maxw: narrow ? 170 : 200,
        wrapAt: narrow ? 11 : 20,
      });
    });
    return G.svg(w, railY + 80, body, "Organization graph");
  }

  // ------------------------------------------------------------------ segment
  function segment(D, r, opt) {
    var s = D.org.segments.filter(function (x) {
      return x.id === r.seg;
    })[0];
    if (!s) return notfound(r);
    var sg = D.org.seg_graphs[s.id],
      narrow = opt.width && opt.width < 760,
      dir = narrow ? "TB" : "LR";
    var nodes = sg.nodes.map(function (n) {
      return { id: n.id };
    });
    sg.edges.forEach(function (e) {
      if (
        e.from.indexOf("start:") === 0 &&
        !nodes.some(function (n) {
          return n.id === e.from;
        })
      )
        nodes.push({ id: e.from, layer: 0 });
    });
    var lay = G.layered(nodes, sg.edges, {
      dir: dir,
      gapMain: narrow ? 180 : 250,
      gapCross: narrow ? 220 : 160,
      pad: 100,
    });
    if (!narrow && lay.layers > 1 && lay.w + 200 > (opt.width || 1200) - 60)
      // fit the canvas: tighten the columns, never below 190 px
      lay = G.layered(nodes, sg.edges, {
        dir: dir,
        gapMain: Math.max(
          190,
          ((opt.width || 1200) - 260 - 200) / (lay.layers - 1),
        ),
        gapCross: 160,
        pad: 100,
      });
    var P = lay.pos,
      body = "";
    var stats = {},
      maxSteps = 1,
      maxChecks = 1;
    sg.nodes.forEach(function (n) {
      var st = wfStats(D, n.id);
      stats[n.id] = st;
      maxSteps = Math.max(maxSteps, st.steps);
      maxChecks = Math.max(maxChecks, st.checks);
    });
    function rad(id) {
      var it = D.org.items[id];
      if (!it || it.kind === "component")
        return 24 + Math.min(10, 2 * (it ? it.units.length : 0));
      return Math.round(18 + 14 * Math.sqrt(stats[id].steps / maxSteps));
    }
    sg.edges.forEach(function (e) {
      var st = e.from.indexOf("start:") === 0;
      var p = G.edgePath(
        P[e.from],
        P[e.to],
        dir,
        st ? 14 : rad(e.from) + 4,
        rad(e.to) + 4,
      );
      body += G.edge({
        id: e.from + ">" + e.to,
        from: e.from,
        to: e.to,
        d: p.d,
        mid: p.mid,
        label: st ? [] : e.label,
        kind: e.kind,
        events: e.event ? [e.event] : [],
        seg: s.id,
      });
    });
    nodes.forEach(function (n) {
      if (n.id.indexOf("start:") === 0) {
        var ty = n.id.slice(6);
        body += G.node({
          id: n.id,
          x: P[n.id].x,
          y: P[n.id].y,
          r: 14,
          st: "event",
          kind: "event",
          shape: "tag",
          label: ty,
          wrapAt: 22,
          maxw: 190,
          title: "Event " + ty + " starts a workflow",
        });
        return;
      }
      var it = D.org.items[n.id],
        ext = sg.nodes.filter(function (x) {
          return x.id === n.id;
        })[0].ext,
        st = stats[n.id];
      var comp = it.kind === "component",
        uf = doneFrac(
          D.build.units.filter(function (u) {
            return it.units.indexOf(u.id) >= 0;
          }),
        );
      var sub = ext
        ? "in " + segName(D, it.seg)
        : comp
          ? it.units.length + " build unit" + (it.units.length === 1 ? "" : "s")
          : st.steps + " steps, " + st.checks + " checks";
      body += G.node({
        id: n.id,
        x: P[n.id].x,
        y: P[n.id].y,
        r: rad(n.id),
        lv: 2,
        seg: it.seg,
        st: it.st,
        label: it.name,
        faded: ext,
        sub: sub,
        ring: uf,
        heat: comp ? 0.2 : 0.1 + (0.45 * st.checks) / maxChecks,
        badge: st.runs || null,
        maxw: 190,
        href: itemHref(D, n.id),
        title:
          it.name +
          (ext ? ", in another segment" : ": " + ST[it.st]) +
          ". " +
          (it.summary || ""),
      });
    });
    var cap =
      s.id === "platform"
        ? "An arrow points from a component to the one that needs it. The ring is the share of its build units done."
        : "Tags are events that start a workflow. Size grows with the number of steps, tint with the number of checks; the badge counts runs; the ring is the share of its build units done.";
    var needs = s.needs
      .map(function (id) {
        var d = D.decisions.items.filter(function (x) {
          return x.id === id;
        })[0];
        return d
          ? '<li><a href="#/decisions/' +
              enc(id) +
              '">' +
              esc(d.title) +
              "</a></li>"
          : "";
      })
      .join("");
    var list = s.items
      .map(function (id) {
        var it = D.org.items[id];
        return (
          '<li><a href="' +
          itemHref(D, id) +
          '">' +
          esc(it.name) +
          "</a> " +
          esc(it.summary || "") +
          "</li>"
        );
      })
      .join("");
    var tot = s.items.reduce(
      function (a, id) {
        var x = stats[id] || { steps: 0, checks: 0 };
        return [a[0] + x.steps, a[1] + x.checks];
      },
      [0, 0],
    );
    var lead =
      s.id === "platform"
        ? s.items.length + " components the workflows run on."
        : s.items.length +
          " workflows, " +
          tot[0] +
          " steps, " +
          tot[1] +
          " checks.";
    return (
      head(
        [
          ["Organization", "#/"],
          [s.name, "", s.id],
        ],
        s.name,
        esc(lead),
        null,
        { goal: goal(D, "segment", s), seg: s.id },
      ) +
      (needs
        ? '<div class="callout owner"><h2>Needs you here</h2><ul>' +
          needs +
          "</ul></div>"
        : "") +
      stage(
        G.svg(lay.w + 200, lay.h + 60, body, s.name + " graph"),
        null,
        cap,
        legend(LEG_STATE),
        s.id,
      ) +
      '<details class="block"><summary>' +
      (s.id === "platform" ? "Components" : "Workflows") +
      ' in words</summary><ul class="plain">' +
      list +
      "</ul></details>"
    );
  }
  function segName(D, id) {
    var s = D.org.segments.filter(function (x) {
      return x.id === id;
    })[0];
    return s ? s.name : id;
  }

  // ------------------------------------------------------------------ workflow
  function workflow(D, r, opt) {
    var w = D.workflows[r.wf];
    if (!w) return notfound(r);
    var it = D.org.items[r.wf],
      run = pickRun(D, r.wf, r.run);
    if (r.run && !run) return notfound(r);
    var seg = D.org.segments.filter(function (s) {
      return s.id === it.seg;
    })[0];
    var cr = [
      ["Organization", "#/"],
      [seg.name, "#/s/" + enc(seg.id), seg.id],
      [w.id, r.ops ? wfHref(w.id, { run: r.run }) : "", seg.id, true],
    ];
    if (r.ops) cr.push(["Operations", "", seg.id]);
    var tabs =
      '<nav class="tabs" aria-label="Views of this workflow">' +
      '<a href="' +
      wfHref(w.id, { run: r.run }) +
      '"' +
      (r.ops ? "" : ' aria-current="page"') +
      ">Flow</a>" +
      '<a href="' +
      wfHref(w.id, { run: r.run, ops: true }) +
      '"' +
      (r.ops ? ' aria-current="page"' : "") +
      ">Operations</a></nav>";
    var rs = runsOf(D, w.id);
    var picker =
      '<nav class="runpick" aria-label="Run shown on the graph"><span>Showing</span>' +
      '<a href="' +
      wfHref(w.id, { ops: r.ops }) +
      '"' +
      (!r.run ? ' aria-current="true"' : "") +
      ">" +
      (pickRun(D, w.id, null) ? "the live run" : "the design") +
      "</a>" +
      rs
        .slice(0, 3)
        .concat(run && rs.indexOf(run) < 0 ? [run] : [])
        .map(function (x) {
          return (
            '<a href="' +
            wfHref(w.id, { run: x.id, ops: r.ops }) +
            '"' +
            (r.run === x.id ? ' aria-current="true"' : "") +
            '><span class="st st-' +
            runSt(x) +
            '" aria-hidden="true"></span>run <span class="id">' +
            esc((x.run_id || x.id).slice(0, 8)) +
            "</span>, " +
            esc(
              x.status === "running"
                ? "running"
                : "ended " + (x.end_status || ""),
            ) +
            (rs.indexOf(x) < 0 ? ", superseded" : "") +
            "</a>"
          );
        })
        .join("") +
      "</nav>";
    var st = wfStats(D, w.id);
    var lead =
      esc(w.title) +
      ". " +
      st.steps +
      " steps, " +
      st.checks +
      " checks. " +
      (w.start
        ? "Starts on " + code(w.start) + "."
        : "Called by " +
          (w.called_by
            .map(function (c) {
              return '<a href="' + wfHref(c) + '">' + esc(c) + "</a>";
            })
            .join(", ") || "nobody") +
          ".");
    var g = r.ops ? opsGraph(D, w, r, run, opt) : flowGraph(D, w, r, run, opt);
    var panelHtml = r.sel
      ? r.ops
        ? opsPanel(D, w, r, run)
        : nodePanel(D, w, findNode(w, r.sel), run, wfHref(w.id, { run: r.run }))
      : null;
    if (r.sel && !panelHtml) return notfound(r);
    var runBox = run ? runSummary(D, run, opt.now) : "";
    return (
      head(cr, w.id, lead, tabs + picker, {
        goal: goal(D, "workflow", w),
        seg: seg.id,
        mono: true,
      }) +
      '<div id="runbox">' +
      runBox +
      "</div>" +
      stage(
        g,
        panelHtml,
        r.ops
          ? "Lanes group a step with the code step that proves it. Inputs sit left of the spine, checks and rubrics right, the roles that judge rubrics at the far right." +
              (run
                ? " Size grows with cost; dots above a step count its rounds."
                : "")
          : "The flow in file order. A frame is a loop, fork or group; select its corner button to fold it. A dashed arc on the right is a jump. A double ring marks a floor: a step no change may remove or rewire." +
              (run
                ? " Size grows with cost; dots above a step count its rounds."
                : " The badge counts a step's checks."),
        legend(
          r.ops ? LEG_OPS.concat(run ? LEG_RUN : []) : run ? LEG_RUN : LEG_KIND,
        ),
        seg.id,
      ) +
      workflowInfo(D, w)
    );
  }
  function runSummary(D, run, now) {
    var cur = (run.current || [])
      .map(function (c) {
        return code(c.rel) + " for " + esc(dur(now - c.since));
      })
      .join(", ");
    var ch = run.change,
      chHtml = "";
    if (ch) {
      chHtml =
        "<p>" +
        (run.status === "running" ? "Change in flight" : "Change worktree") +
        ": " +
        code(ch.worktree || "") +
        ". " +
        (ch.files
          ? ch.files.length +
            " changed files" +
            (ch.files.length
              ? ": " +
                ch.files
                  .slice(0, 8)
                  .map(function (f) {
                    return code(f.path);
                  })
                  .join(", ")
              : "")
          : esc(ch.note || "changed files unknown")) +
        "</p>";
      if (ch.rungs && ch.rungs.rows)
        chHtml +=
          "<p>Highest rung touched: <b>" +
          esc(ch.rungs.highest || "none") +
          "</b>" +
          (ch.rungs.refused
            ? ", " + ch.rungs.refused + " outside the improver's rungs"
            : "") +
          ".</p>";
      else if (ch.rungs && ch.rungs.note)
        chHtml += "<p>" + esc(ch.rungs.note) + "</p>";
    }
    var ev = (run.events || [])
      .slice(-12)
      .reverse()
      .map(function (e) {
        return "<li>" + esc(e.text) + "</li>";
      })
      .join("");
    var rst = runSt(run),
      took = run.last && run.started ? dur(run.last - run.started) : null;
    return (
      '<section class="runbox' +
      (run.status === "running" ? " live" : rst === "failed" ? " bad" : "") +
      '"><h2>' +
      (run.status === "running"
        ? "Running now"
        : "Run " +
          '<span class="id">' +
          esc((run.run_id || "").slice(0, 8)) +
          "</span>") +
      " " +
      chip(
        rst === "active" ? "active" : rst,
        run.status === "running"
          ? "running"
          : "ended " + (run.end_status || run.status),
      ) +
      "</h2>" +
      kv([
        ["step calls", String(run.calls || 0), run.calls || 0],
        [run.cost_partial ? "cost, partial" : "cost", usd(run.cost_usd || 0)],
        ["time", took],
      ]) +
      "<p>" +
      (cur ? "Current step: " + cur + ". " : "") +
      (run.title ? "Input: " + esc(run.title) + "." : "") +
      "</p>" +
      chHtml +
      (run.problems && run.problems.length
        ? '<p class="warn">Ledger problem: ' +
          esc(run.problems.join("; ")) +
          "</p>"
        : "") +
      '<details><summary>Latest ledger entries</summary><ol class="events">' +
      ev +
      "</ol></details>" +
      history(D, run) +
      "</section>"
    );
  }
  function history(D, run) {
    var old = olderRuns(D, run),
      latest = runs(D).filter(function (x) {
        return x.workflow === run.workflow;
      })[0];
    if (!old.length) return "";
    return (
      '<details class="hist"><summary>History: ' +
      old.length +
      " other run" +
      (old.length === 1 ? "" : "s") +
      " of " +
      esc(run.workflow) +
      "</summary><ul>" +
      old
        .map(function (x) {
          return (
            '<li><a href="' +
            wfHref(run.workflow, { run: x.id }) +
            '">run <span class="id">' +
            esc(String(x.run_id || x.id).slice(0, 8)) +
            "</span></a>, " +
            esc(
              x.status === "running"
                ? "running"
                : "ended " + (x.end_status || ""),
            ) +
            (latest && x.id === latest.id ? ", latest" : ", superseded") +
            "</li>"
          );
        })
        .join("") +
      "</ul></details>"
    );
  }
  function findNode(w, key) {
    return (
      walk(w.tree).filter(function (n) {
        return n.key === key;
      })[0] || null
    );
  }

  function nodeSub(n) {
    var bits = [];
    if (n.kind === "call") bits.push("calls " + n.call.name);
    else if (n.kind === "emit") bits.push("emits " + n.emits.type);
    else if (n.kind === "gate") bits.push("you decide");
    else if (n.kind === "listen") bits.push("waits for " + n.listens.type);
    else if (n.kind === "raise")
      bits.push("escalates to " + (n.raise.to || "?"));
    else if (n.kind === "switch") bits.push("chooses a path");
    else bits.push(n.by ? "by " + n.by : n.label);
    if (n.role) bits.push(n.role);
    if (n.if_read) bits.push("if " + n.if_read);
    return bits.join(", ");
  }
  // kind and shape of a step in the graphs: the shape stays when a run colors the state
  function kindOf(n) {
    if (n.kind === "gate" || n.by === "human") return "gate";
    if (n.kind === "emit" || n.kind === "listen" || n.kind === "wait")
      return "event";
    if (n.kind === "raise") return "raise";
    if (n.kind === "call") return "call";
    return "step";
  }
  function shapeOf(n) {
    var k = kindOf(n);
    return k === "gate"
      ? "hex"
      : k === "event"
        ? "tag"
        : k === "step" && (n.by === "code" || n.kind === "switch")
          ? "square"
          : null;
  }
  function byCls(n) {
    return kindOf(n) === "step"
      ? n.by === "code" || n.kind === "switch"
        ? "by-code"
        : "by-model"
      : "";
  }
  // the state of a folded container in a run: the worst of what it holds
  function rollup(n, tasks) {
    var sts = walk([n])
      .filter(function (c) {
        return !c.children && !c.branches;
      })
      .map(function (c) {
        return taskState(tasks[c.key], c);
      });
    var order = [
      "failed",
      "gate",
      "active",
      "escalated",
      "interrupted",
      "done",
      "skipped",
      "queued",
    ];
    for (var i = 0; i < order.length; i++)
      if (sts.indexOf(order[i]) >= 0) return order[i];
    return "queued";
  }
  function flowGraph(D, w, r, run, opt) {
    var tree = JSON.parse(JSON.stringify(w.tree)),
      collapsed = (opt && opt.collapsed) || {};
    walk(tree).forEach(function (n) {
      n.sub = nodeSub(n);
    });
    var F = G.flow(tree, { collapsed: collapsed });
    var body = "",
      tasks = tasksFor(run, w.id),
      maxUsd = 0;
    Object.keys(tasks).forEach(function (k) {
      maxUsd = Math.max(maxUsd, tasks[k].usd || 0);
    });
    F.frames
      .slice()
      .sort(function (a, b) {
        return a.depth - b.depth;
      })
      .forEach(function (f) {
        var sel = r.sel === f.n.key;
        body +=
          '<a class="frame-link" href="' +
          wfHref(w.id, { run: r.run, sel: f.n.key }) +
          '"><title>' +
          esc(f.n.name + ": " + f.head + ". " + stepGoal(f.n)) +
          "</title>" +
          '<rect class="frame' +
          (f.rework ? " rework" : "") +
          (sel ? " sel" : "") +
          '" data-node="' +
          esc(f.n.key) +
          '" x="' +
          f.x +
          '" y="' +
          f.y +
          '" width="' +
          G.r1(f.w) +
          '" height="' +
          G.r1(f.h) +
          '" rx="14"/>' +
          '<text class="fhead" x="' +
          (f.x + 40) +
          '" y="' +
          (f.y + 24) +
          '"><tspan class="fname">' +
          esc(f.n.name) +
          "</tspan>  " +
          esc(f.head) +
          "</text></a>" +
          tog(f.n.key, f.x + 10, f.y + 9, true, f.n.name);
        if (f.n.loop) {
          var lx = f.x - 10,
            y1 = f.y + f.h - 12,
            y2 = f.y + 18;
          body +=
            '<g class="edge k-loop" data-edge="loop:' +
            esc(f.n.key) +
            '" data-from="' +
            esc(f.n.key) +
            '" data-to="' +
            esc(f.n.key) +
            '"><path class="ep" d="M' +
            (f.x + 8) +
            "," +
            y1 +
            " H" +
            lx +
            " V" +
            y2 +
            " H" +
            (f.x + 2) +
            '" marker-end="url(#arrow)"/></g>';
        }
      });
    F.seq.forEach(function (s) {
      var d =
        "M" +
        G.r1(s.from.x) +
        "," +
        G.r1(s.from.y) +
        " C" +
        G.r1(s.from.x) +
        "," +
        G.r1(s.from.y + 16) +
        " " +
        G.r1(s.to.x) +
        "," +
        G.r1(s.to.y - 16) +
        " " +
        G.r1(s.to.x) +
        "," +
        G.r1(s.to.y - 4);
      body +=
        '<g class="edge k-seq" data-edge="seq:' +
        esc(s.b || s.a + "/") +
        '"' +
        (s.a ? ' data-from="' + esc(s.a) + '"' : "") +
        (s.b ? ' data-to="' + esc(s.b) + '"' : "") +
        '><path class="ep" d="' +
        d +
        '" marker-end="url(#arrow)"/></g>';
    });
    F.jumps.forEach(function (j) {
      var d =
        "M" +
        G.r1(j.a.x + 22) +
        "," +
        G.r1(j.a.y) +
        " H" +
        j.x +
        " V" +
        G.r1(j.b.y) +
        " H" +
        G.r1(j.b.x + 26);
      body +=
        '<g class="edge k-jump dashed" data-edge="jump:' +
        esc(j.from + ">" + j.to) +
        '" data-from="' +
        esc(j.from) +
        '" data-to="' +
        esc(j.to) +
        '"><path class="ep" d="' +
        d +
        '" marker-end="url(#arrow)"/>' +
        '<text class="elab" x="' +
        (j.x + 8) +
        '" y="' +
        G.r1((j.a.y + j.b.y) / 2) +
        '">' +
        esc(j.label) +
        "</text></g>";
    });
    F.leaves.forEach(function (l) {
      var n = l.n,
        folded = !!(n.children || n.branches),
        t = tasks[n.key];
      var st = run
        ? folded
          ? rollup(n, tasks)
          : taskState(t, n)
        : folded
          ? "queued"
          : designState(n);
      var usd0 = t && t.usd ? t.usd : 0,
        rr =
          run && maxUsd && !folded
            ? Math.round(12 + 12 * Math.sqrt(usd0 / maxUsd))
            : F.R;
      var nacc = (n.acceptance || []).length;
      var sub = folded
        ? (n.children ? n.children.length : n.branches.length) +
          (n.children ? " steps" : " branches") +
          " folded"
        : n.sub;
      body += G.node({
        id: n.key,
        x: l.x,
        y: l.y,
        r: rr,
        st: st,
        kind: folded ? null : kindOf(n),
        shape: folded ? "square" : shapeOf(n),
        label: n.name,
        sub: sub,
        labelPos: "right",
        floor: n.floor,
        lv: 3,
        cls: (r.sel === n.key ? "sel " : "") + byCls(n),
        ticks: t ? t.starts : 0,
        badge: !run && nacc ? nacc : null,
        heat: run && maxUsd ? 0.1 + (0.4 * usd0) / maxUsd : null,
        maxw: 280,
        href: wfHref(w.id, { run: r.run, sel: n.key }),
        title: n.name + ", " + n.sub + ". " + stepGoal(n),
      });
      if (folded) body += tog(n.key, l.x - F.R - 30, l.y - 10, false, n.name);
    });
    return G.svg(
      F.w + 20,
      F.h,
      '<g class="seg-' + esc(segOf(D, w.id)) + '">' + body + "</g>",
      "Flow of " + w.id,
    );
  }
  // fold button of a container; app.js handles it, the page works without it
  function tog(key, x, y, open, name) {
    return (
      '<g class="tog" role="button" tabindex="0" data-toggle="' +
      esc(key) +
      '" aria-expanded="' +
      open +
      '" aria-label="' +
      (open ? "Fold " : "Unfold ") +
      esc(name) +
      '" transform="translate(' +
      x +
      "," +
      y +
      ')">' +
      "<title>" +
      (open ? "Fold " : "Unfold ") +
      esc(name) +
      '</title><rect width="20" height="20" rx="6"/><path d="M5,10 H15' +
      (open ? "" : " M10,5 V15") +
      '"/></g>'
    );
  }

  // operations: steps grouped in lanes (a step and the code steps that prove it), with inputs, outputs, checks, rubrics, gates and judges
  function phases(leaves) {
    var out = [];
    leaves.forEach(function (n) {
      var cur = out[out.length - 1],
        parent = n.key.split("/").slice(0, -1).join("/");
      if (cur && cur.parent === parent && n.name.indexOf(cur.head + "-") === 0)
        cur.items.push(n);
      else out.push({ head: n.name, parent: parent, items: [n] });
    });
    return out;
  }
  var OX = { lane: 22, io: 336, spine: 500, acc: 660, judge: 1000, w: 1190 };
  function opsModel(D, w) {
    var rows = [],
      judges = {},
      y = 56;
    var leaves = leavesOf(w),
      ph = phases(leaves);
    ph.forEach(function (p) {
      p.top = y;
      p.items.forEach(function (n) {
        var i = leaves.indexOf(n),
          io = [];
        if (i === 0)
          io.push(
            w.start
              ? {
                  id: "io:start",
                  label: w.start,
                  st: "event",
                  kind: "event",
                  shape: "tag",
                  dir: "in",
                  about: "starts this workflow",
                }
              : {
                  id: "io:caller",
                  label: "called by " + (w.called_by.join(", ") || "nobody"),
                  st: "role",
                  kind: "role",
                  dir: "in",
                  href: w.called_by[0]
                    ? wfHref(w.called_by[0], { ops: true })
                    : null,
                  about: "the workflows that call this one",
                },
          );
        if (n.listens)
          io.push({
            id: "io:" + n.key + ":l",
            label: n.listens.type,
            st: "event",
            kind: "event",
            shape: "tag",
            dir: "in",
            about:
              n.kind === "gate"
                ? "your signed decision"
                : "an event it waits for",
          });
        if (n.emits)
          io.push({
            id: "io:" + n.key + ":e",
            label: n.emits.type,
            st: "event",
            kind: "event",
            shape: "tag",
            dir: "out",
            about: n.emits.starts.length
              ? "starts " + n.emits.starts.join(", ")
              : "no workflow listens",
          });
        if (n.call)
          io.push({
            id: "io:" + n.key + ":c",
            label: n.call.name,
            st: "code",
            kind: "call",
            dir: "out",
            href: n.call.known ? wfHref(n.call.name, { ops: true }) : null,
            about: "a call, version " + n.call.version,
          });
        if (n.raise)
          io.push({
            id: "io:" + n.key + ":r",
            label: n.raise.to || "?",
            st: "escalated",
            kind: "raise",
            dir: "out",
            about: "escalation: " + n.raise.title,
          });
        var acc = (n.acceptance || []).map(function (a, j) {
          var o = { id: "acc:" + n.key + ":" + j, a: a, idx: j };
          if (a.type === "check") {
            o.label = a.id;
            o.shape = "square";
            o.st = "check";
            o.kind = "check";
            o.sub = (a.cls || "unregistered") + " check";
          } else if (a.type === "rubric") {
            o.label = a.title || a.path;
            o.shape = "diamond";
            o.st = "rubric";
            o.kind = "rubric";
            o.sub = "rubric, judged by " + (a.judge || "?");
            if (a.judge) (judges[a.judge] = judges[a.judge] || []).push(o.id);
          } else {
            o.label = a.text;
            o.st = "human";
            o.kind = "gate";
            o.shape = "hex";
            o.sub = "your decision";
          }
          return o;
        });
        var hgt = Math.max(118, Math.max(io.length, acc.length) * 54 + 30);
        rows.push({
          n: n,
          y: y + 34,
          top: y,
          io: io,
          acc: acc,
          h: hgt,
          phase: p,
        });
        y += hgt;
      });
      p.h = y - p.top;
      y += 10;
    });
    return { rows: rows, judges: judges, phases: ph, h: y + 20 };
  }
  function opsGraph(D, w, r, run) {
    var M = opsModel(D, w),
      body = "",
      tasks = tasksFor(run, w.id),
      maxUsd = 0;
    Object.keys(tasks).forEach(function (k) {
      maxUsd = Math.max(maxUsd, tasks[k].usd || 0);
    });
    var jy = {},
      jk = Object.keys(M.judges);
    function accY(id) {
      var y = 0;
      M.rows.forEach(function (row) {
        row.acc.forEach(function (o, k) {
          if (o.id === id) y = row.y + k * 54;
        });
      });
      return y;
    }
    jk.forEach(function (j) {
      var ys = M.judges[j].map(accY);
      jy[j] =
        ys.reduce(function (a, b) {
          return a + b;
        }, 0) / ys.length;
    });
    jk.sort(function (a, b) {
      return jy[a] - jy[b];
    });
    for (var i = 1; i < jk.length; i++)
      if (jy[jk[i]] < jy[jk[i - 1]] + 90) jy[jk[i]] = jy[jk[i - 1]] + 90;
    var hh = Math.max(M.h, jk.length ? jy[jk[jk.length - 1]] + 80 : 0);
    body +=
      '<text class="colhead" x="' +
      OX.io +
      '" y="28" text-anchor="end">Inputs and outputs</text><text class="colhead" x="' +
      OX.spine +
      '" y="28" text-anchor="middle">Steps</text>' +
      '<text class="colhead" x="' +
      (OX.acc - 14) +
      '" y="28">Checks and rubrics</text>' +
      (jk.length
        ? '<text class="colhead" x="' +
          (OX.judge - 18) +
          '" y="28">Judges</text>'
        : "");
    M.phases.forEach(function (p, k) {
      var cnt = p.items.length,
        nm = p.parent ? p.parent.split("/").pop() : "";
      body +=
        '<g class="lanegrp"><rect class="lane" x="10" y="' +
        (p.top - 4) +
        '" width="' +
        (OX.w - 20) +
        '" height="' +
        (p.h - 2) +
        '" rx="12" style="opacity:' +
        (k % 2 ? 0.55 : 1) +
        '"/>' +
        '<rect class="lane-rule" x="10" y="' +
        (p.top + 8) +
        '" width="4" height="' +
        Math.max(10, p.h - 26) +
        '" rx="2"/>' +
        '<text class="lanelab" x="' +
        (OX.lane + 4) +
        '" y="' +
        (p.top + 24) +
        '">' +
        esc(G.fit(p.head, 140, 13)) +
        "</text>" +
        '<text class="lanesub" x="' +
        (OX.lane + 4) +
        '" y="' +
        (p.top + 42) +
        '">' +
        esc(cnt + " step" + (cnt === 1 ? "" : "s") + (nm ? ", in " + nm : "")) +
        "</text></g>";
    });
    var prev = null;
    M.rows.forEach(function (row) {
      var n = row.n,
        sp = { x: OX.spine, y: row.y };
      if (prev) {
        var p = G.edgePath(prev.p, sp, "TB", 20, 20);
        body += G.edge({
          id: "seq:" + n.key,
          from: "step:" + prev.key,
          to: "step:" + n.key,
          d: p.d,
          mid: p.mid,
          kind: "seq",
        });
      }
      prev = { p: sp, key: n.key };
      row.io.forEach(function (o, k) {
        o.x = OX.io;
        o.y = row.y + k * 54;
        var pth =
          o.dir === "in"
            ? G.edgePath(o, sp, "LR", 16, 22)
            : G.edgePath(sp, o, "LR", 22, 16);
        body += G.edge({
          id: (o.dir === "in" ? "in:" : "out:") + o.id,
          from: o.dir === "in" ? o.id : "step:" + n.key,
          to: o.dir === "in" ? "step:" + n.key : o.id,
          d: pth.d,
          mid: pth.mid,
          kind: o.dir === "in" ? "start" : "event",
          events: [o.label],
        });
      });
      row.acc.forEach(function (o, k) {
        o.x = OX.acc;
        o.y = row.y + k * 54;
        var pth = G.edgePath(sp, o, "LR", 22, 16);
        body += G.edge({
          id: "acc:" + n.key + ":" + k,
          from: "step:" + n.key,
          to: o.id,
          d: pth.d,
          mid: pth.mid,
          kind: "acc",
        });
        if (o.a.type === "rubric" && o.a.judge) {
          var pj = G.edgePath(
            { x: OX.acc + 262, y: o.y },
            { x: OX.judge, y: jy[o.a.judge] },
            "LR",
            4,
            20,
          );
          body += G.edge({
            id: "judge:" + o.id,
            from: o.id,
            to: "judge:" + o.a.judge,
            d: pj.d,
            mid: pj.mid,
            kind: "judge",
          });
        }
      });
    });
    M.rows.forEach(function (row) {
      var n = row.n,
        t = tasks[n.key];
      var st = run ? taskState(t, n) : designState(n),
        usd0 = t && t.usd ? t.usd : 0;
      var rr =
        run && maxUsd ? Math.round(13 + 11 * Math.sqrt(usd0 / maxUsd)) : 18;
      body += G.node({
        id: "step:" + n.key,
        x: OX.spine,
        y: row.y,
        r: rr,
        st: st,
        kind: kindOf(n),
        shape: shapeOf(n),
        label: n.name,
        sub: nodeSub(n),
        labelPos: "below",
        wrapAt: 26,
        floor: n.floor,
        lv: 2,
        maxw: 230,
        cls: (r.sel === "step:" + n.key ? "sel " : "") + byCls(n),
        ticks: t ? t.starts : 0,
        heat: run && maxUsd ? 0.1 + (0.4 * usd0) / maxUsd : null,
        href: wfHref(w.id, { run: r.run, ops: true, sel: "step:" + n.key }),
        title: n.name + ", " + nodeSub(n) + ". " + stepGoal(n),
      });
      row.io.forEach(function (o) {
        body += G.node({
          id: o.id,
          x: o.x,
          y: o.y,
          r: 13,
          st: o.st,
          kind: o.kind,
          shape: o.shape,
          label: o.label,
          labelPos: "left",
          maxw: 165,
          cls: r.sel === o.id ? "sel" : "",
          href: wfHref(w.id, { run: r.run, ops: true, sel: o.id }),
          title: o.label + (o.about ? ", " + o.about : ""),
        });
      });
      row.acc.forEach(function (o) {
        var ast = o.st;
        if (t && o.a.type === "check" && t.checks && o.a.id in t.checks)
          ast = t.checks[o.a.id] === true ? "done" : "failed";
        if (t && o.a.type === "rubric" && t.judges && String(o.idx) in t.judges)
          ast =
            t.judges[String(o.idx)] === "pass"
              ? "done"
              : t.judges[String(o.idx)] === "fail"
                ? "failed"
                : "queued";
        body += G.node({
          id: o.id,
          x: o.x,
          y: o.y,
          r: 12,
          st: ast,
          kind: o.kind,
          shape: o.shape,
          label: o.label,
          sub: o.sub,
          labelPos: "right",
          maxw: 236,
          cls: r.sel === o.id ? "sel" : "",
          href: wfHref(w.id, { run: r.run, ops: true, sel: o.id }),
          title: o.label + ", " + o.sub,
        });
      });
    });
    jk.forEach(function (j) {
      body += G.node({
        id: "judge:" + j,
        x: OX.judge,
        y: jy[j],
        r: 16,
        st: "role",
        kind: "role",
        label: j,
        sub:
          "judges " +
          M.judges[j].length +
          " rubric" +
          (M.judges[j].length === 1 ? "" : "s"),
        labelPos: "right",
        lv: 2,
        maxw: 140,
        badge: M.judges[j].length,
        cls: r.sel === "judge:" + j ? "sel" : "",
        href: wfHref(w.id, { run: r.run, ops: true, sel: "judge:" + j }),
        title: "Role " + j,
      });
    });
    return G.svg(
      OX.w,
      hh,
      '<g class="seg-' + esc(segOf(D, w.id)) + '">' + body + "</g>",
      "Operations of " + w.id,
    );
  }
  function opsPanel(D, w, r, run) {
    var id = r.sel,
      close = wfHref(w.id, { run: r.run, ops: true });
    if (id.indexOf("step:") === 0) {
      var n = findNode(w, id.slice(5));
      return n ? nodePanel(D, w, n, run, close) : null;
    }
    var M = opsModel(D, w),
      found = null;
    M.rows.forEach(function (row) {
      row.io.concat(row.acc).forEach(function (o) {
        if (o.id === id) found = { o: o, n: row.n };
      });
    });
    if (id.indexOf("judge:") === 0) {
      var role = id.slice(6);
      if (!M.judges[role]) return null;
      var rr = w.roles.filter(function (x) {
        return x.id === role;
      })[0] || { id: role };
      var list = M.judges[role].map(function (aid) {
        var f = null;
        M.rows.forEach(function (row) {
          row.acc.forEach(function (o) {
            if (o.id === aid) f = { o: o, n: row.n };
          });
        });
        return f;
      });
      return panel({
        title: role,
        mono: true,
        close: close,
        kind: "role, judges rubrics",
        goal:
          "Judges " +
          list.length +
          " rubric" +
          (list.length === 1 ? "" : "s") +
          " of this workflow against their rules.",
        secs: {
          what: dl([
            [
              "Escalates to",
              rr.chain
                ? esc(rr.chain.join(" then ")) || "nobody"
                : esc(rr.about || ""),
            ],
            ["May spawn", rr.may_spawn ? esc(rr.may_spawn.join(", ")) : null],
            [
              "Rungs",
              rr.rungs && rr.rungs.length ? esc(rr.rungs.join(", ")) : null,
            ],
          ]),
          checks:
            "<ul>" +
            list
              .map(function (f) {
                return (
                  '<li><a href="' +
                  wfHref(w.id, { run: r.run, ops: true, sel: f.o.id }) +
                  '">' +
                  esc(f.o.label) +
                  "</a> on " +
                  code(f.n.key) +
                  "</li>"
                );
              })
              .join("") +
            "</ul>",
        },
      });
    }
    if (!found) return null;
    var o = found.o,
      nn = found.n,
      t = tasksFor(run, w.id)[nn.key];
    if (o.a) return accPanel(o.a, o.idx, nn, t, close, w, r);
    var stepLink =
      '<a href="' +
      wfHref(w.id, { run: r.run, ops: true, sel: "step:" + nn.key }) +
      '">' +
      esc(nn.name) +
      "</a>";
    return panel({
      title: o.label,
      mono: true,
      close: close,
      kind:
        o.kind === "event"
          ? "event"
          : o.kind === "raise"
            ? "escalation"
            : o.kind === "call"
              ? "call"
              : "connection",
      goal: o.about
        ? o.about.charAt(0).toUpperCase() + o.about.slice(1) + "."
        : "",
      secs: {
        what: dl([
          [
            "Open",
            o.href
              ? '<a href="' +
                o.href +
                '">' +
                esc(o.label.replace(/^called by /, "")) +
                " operations</a>"
              : null,
          ],
        ]),
        inputs: o.dir === "out" ? "<p>From the step " + stepLink + ".</p>" : "",
        outputs: o.dir === "in" ? "<p>Into the step " + stepLink + ".</p>" : "",
      },
    });
  }
  function accPanel(a, idx, n, t, close, w, r) {
    var res = "",
      rst = null;
    if (t && a.type === "check" && t.checks && a.id in t.checks) {
      res =
        t.checks[a.id] === true ? "passed in this run" : "failed in this run";
      rst = t.checks[a.id] === true ? "done" : "failed";
    }
    if (t && a.type === "rubric" && t.judges && String(idx) in t.judges) {
      res = "verdict in this run: " + t.judges[String(idx)];
      rst =
        t.judges[String(idx)] === "pass"
          ? "done"
          : t.judges[String(idx)] === "fail"
            ? "failed"
            : "queued";
    }
    var back =
      '<a href="' +
      wfHref(w.id, { run: r.run, ops: true, sel: "step:" + n.key }) +
      '">' +
      esc(n.name) +
      "</a>";
    var hist = res
      ? "<p>" + esc(res.charAt(0).toUpperCase() + res.slice(1)) + ".</p>"
      : t
        ? "<p>No result recorded in this run.</p>"
        : "";
    if (a.type === "check")
      return panel({
        title: a.id,
        mono: true,
        close: close,
        kind: "check, " + (a.cls || "not registered in the manifest"),
        st: rst ? [rst, res] : null,
        goal:
          "Accepts the step " +
          n.name +
          " only if this check passes" +
          (a.cls === "fact"
            ? ", reading the code step's own result."
            : a.cls === "shape"
              ? ", validating the shape of its output."
              : "."),
        secs: {
          what: dl([
            [
              "Class",
              a.cls === "fact"
                ? "fact: reads a code step's own result, so it can be trusted"
                : a.cls === "shape"
                  ? "shape: validates the step's output, which is a claim"
                  : esc(a.cls || "not registered"),
            ],
          ]),
          inputs:
            "<p>The result of " +
            back +
            (a.reads ? ": " + a.reads : "") +
            "</p>",
          history: hist,
        },
      });
    if (a.type === "rubric")
      return panel({
        title: a.title || a.path,
        close: close,
        kind: "rubric, judged by " + (a.judge || "?"),
        st: rst ? [rst, res] : null,
        goal:
          "A judge reads the output of " +
          n.name +
          " against " +
          a.rules.length +
          " rule" +
          (a.rules.length === 1 ? "" : "s") +
          (a.sample != null
            ? ", on " + Math.round(a.sample * 100) + " percent of runs"
            : "") +
          ".",
        secs: {
          what: dl([
            ["Judged by", esc(a.judge || "?")],
            ["File", code(a.path)],
          ]),
          inputs: "<p>The output of " + back + ".</p>",
          checks:
            '<ol class="rules">' +
            a.rules
              .map(function (x) {
                return "<li>" + x + "</li>";
              })
              .join("") +
            "</ol>",
          history: hist,
        },
      });
    return panel({
      title: "Your decision",
      close: close,
      kind: "human item",
      goal: a.text,
      secs: { what: dl([["On step", back]]) },
    });
  }

  function accList(acc) {
    return (acc || [])
      .map(function (a) {
        var k =
          a.type === "check"
            ? "check"
            : a.type === "rubric"
              ? "rubric"
              : "gate";
        var body =
          a.type === "check"
            ? "check " +
              code(a.id) +
              ", " +
              esc(a.cls || "not registered") +
              (a.reads
                ? '<br><span class="muted">reads ' + a.reads + "</span>"
                : "")
            : a.type === "rubric"
              ? "rubric " +
                code(a.path) +
                ", judged by " +
                esc(a.judge || "?") +
                "<details><summary>" +
                esc(a.title) +
                '</summary><ol class="rules">' +
                a.rules
                  .map(function (x) {
                    return "<li>" + x + "</li>";
                  })
                  .join("") +
                "</ol></details>"
              : "your decision: " + esc(a.text);
        return (
          '<li class="k-' +
          k +
          '"><span class="kmark" aria-hidden="true"></span><span>' +
          body +
          "</span></li>"
        );
      })
      .join("");
  }
  function prevOf(w, n) {
    var ls = leavesOf(w),
      i = ls.indexOf(
        ls.filter(function (x) {
          return x.key === n.key;
        })[0],
      );
    return i > 0 ? ls[i - 1] : null;
  }
  function nodePanel(D, w, n, run, close) {
    if (!n) return null;
    var what = [];
    if (n.role)
      what.push([
        "Role",
        code(n.role) +
          (n.chain && n.chain.length
            ? ", escalates to " + esc(n.chain.join(" then "))
            : "") +
          (n.role_known === false ? " (not in the manifest)" : ""),
      ]);
    if (n.by) what.push(["Done by", esc(n.by)]);
    if (n.signer) what.push(["Signer", esc(n.signer)]);
    if (n.command)
      what.push([
        "Command",
        code(n.command) + (n.no_await ? " (starts and moves on)" : ""),
      ]);
    if (n.loop) {
      what.push([
        "Loop",
        code("for " + n.loop.each + " in " + n.loop.in) +
          ", " +
          esc(n.loop.bound),
      ]);
      if (n.loop.while_read)
        what.push([
          "While",
          esc(n.loop.while_read) + "<br>" + code(n.loop.while),
        ]);
    }
    if (n.timeout) what.push(["Times out after", esc(n.timeout)]);
    if (n.network) what.push(["Network", code(n.network)]);
    if (n.floor != null)
      what.push([
        "Floor",
        n.floor
          ? "yes: it cannot be removed or rewired; the improver may change only its brief"
          : "no",
      ]);
    what.push(["Task key", code(n.key)]);
    var ins = [],
      pv = prevOf(w, n);
    if (pv && !n.children && !n.branches)
      ins.push([
        "After",
        '<a href="' +
          wfHref(w.id, {
            run:
              run && run.id !== (pickRun(D, w.id, null) || {}).id
                ? run.id
                : null,
            sel: pv.key,
          }) +
          '">' +
          esc(pv.name) +
          "</a>",
      ]);
    if (n.if_read)
      ins.push(["Runs if", esc(n.if_read) + "<br>" + code(n["if"])]);
    if (n.listens)
      ins.push([
        "Waits for",
        code(n.listens.type) +
          (n.listens.until ? ", until " + code(n.listens.until) : ""),
      ]);
    if (n.call) ins.push(["Input", code(n.call.input)]);
    var outs = [];
    if (n.call)
      outs.push([
        "Calls",
        (n.call.known
          ? '<a href="' + wfHref(n.call.name) + '">' + esc(n.call.name) + "</a>"
          : esc(n.call.name)) +
          " version " +
          esc(n.call.version),
      ]);
    if (n.emits)
      outs.push([
        "Emits",
        code(n.emits.type) +
          ", " +
          (n.emits.starts.length
            ? "starts " +
              n.emits.starts
                .map(function (x) {
                  return '<a href="' + wfHref(x) + '">' + esc(x) + "</a>";
                })
                .join(", ")
            : "no workflow listens"),
      ]);
    if (n.raise)
      outs.push([
        "Raises",
        esc(n.raise.title) +
          ", status " +
          esc(n.raise.status) +
          ", to " +
          esc(n.raise.to || "?"),
      ]);
    if (n.cases)
      outs.push([
        "Cases",
        "<ul>" +
          n.cases
            .map(function (c) {
              return (
                "<li><b>" +
                esc(c.name) +
                "</b>: " +
                (c.when_read ? "when " + esc(c.when_read) : "otherwise") +
                ", then " +
                code(c.then) +
                "</li>"
              );
            })
            .join("") +
          "</ul>",
      ]);
    if (n.then) outs.push(["Then", code(n.then)]);
    var bo =
      n.brief && n.brief.html
        ? (n.brief.html.split(/<h5[^>]*>Output<\/h5>/)[1] || "").split(/<h5/)[0]
        : "";
    if (strip(bo)) outs.push(["Output", esc(strip(bo))]);
    var t = tasksFor(run, w.id)[n.key],
      hist = "",
      st = null;
    if (run) {
      st = t ? [taskState(t, n), t.state] : null;
      hist = t
        ? kv([
            ["rounds", String(t.starts), t.starts],
            ["cost", t.usd ? usd(t.usd) : "0 USD"],
            ["acceptance", t.accept || "not judged"],
          ])
        : "<p>Not reached in this run.</p>";
    }
    var ms = (n.metrics || [])
      .map(function (m) {
        return (
          "<li>" +
          code(m.id) +
          (m.formula
            ? ": " +
              esc(m.formula) +
              " (" +
              esc(m.unit) +
              ", " +
              esc(m.better) +
              " is better)"
            : ": not in a catalog") +
          (m.target ? ", target " + esc(m.target) : "") +
          ", latest " +
          esc(metricTxt(D, m.id)) +
          "</li>"
        );
      })
      .join("");
    if (ms) hist += "<p>Metrics it feeds:</p><ul>" + ms + "</ul>";
    var acc = accList(n.acceptance);
    var brief = n.brief
      ? '<details class="brief"><summary>Full brief ' +
        code(n.brief.path) +
        "</summary>" +
        (n.brief.html || "<p>The brief file is missing.</p>") +
        "</details>"
      : "";
    var ops =
      n.children || n.branches
        ? ""
        : '<p><a href="' +
          wfHref(w.id, {
            ops: true,
            sel: "step:" + n.key,
            run:
              run && run.id !== (pickRun(D, w.id, null) || {}).id
                ? run.id
                : null,
          }) +
          '">See its checks and judges</a></p>';
    return panel({
      title: n.name,
      mono: true,
      close: close,
      kind: n.label + (n.floor ? ", floor" : ""),
      st: st,
      goal: goal(D, "step", n),
      secs: {
        what: dl(what),
        inputs: dl(ins),
        outputs: dl(outs),
        checks: acc ? '<ul class="acc">' + acc + "</ul>" + ops : ops,
        history: hist,
        extra: brief,
      },
    });
  }

  function workflowInfo(D, w) {
    var facts = [];
    facts.push(
      w.start
        ? "Starts on " + code(w.start)
        : "Called by " + (w.called_by.join(", ") || "nobody"),
    );
    if (w.policy.length)
      facts.push("Policies: " + w.policy.map(code).join(", "));
    facts.push(
      "Floors (" +
        esc(w.floors_src) +
        "): " +
        (w.floors.map(code).join(", ") || "none"),
    );
    if (w.no_listener.length)
      facts.push(
        "Emits with no listener: " + w.no_listener.map(code).join(", "),
      );
    facts.push("File: " + code(w.path) + ", version " + esc(w.version));
    if (!w.registered) facts.push("Designed, not registered in the manifest");
    var mt = w.metrics
      .map(function (m) {
        return (
          "<tr><td>" +
          code(m.id) +
          "</td><td>" +
          esc(m.formula || "not in a catalog") +
          "</td><td>" +
          esc(m.unit || "") +
          "</td><td>" +
          esc(m.better || "") +
          "</td><td>" +
          esc(m.target || "none") +
          "</td><td>" +
          esc(metricTxt(D, m.id)) +
          "</td><td>" +
          esc(m.used_by.join(", ")) +
          "</td></tr>"
        );
      })
      .join("");
    var rt = w.roles
      .map(function (r) {
        return (
          "<tr><td>" +
          code(r.id) +
          "</td><td>" +
          esc(r.chain ? r.chain.join(" then ") : r.about || "") +
          "</td><td>" +
          esc((r.may_spawn || []).join(", ")) +
          "</td><td>" +
          esc((r.rungs || []).join(", ")) +
          "</td></tr>"
        );
      })
      .join("");
    return (
      '<div class="more">' +
      '<details class="block"><summary>What it does</summary>' +
      (w.describe ? "<p>" + esc(w.describe) + "</p>" : "") +
      "<ul>" +
      facts
        .map(function (f) {
          return "<li>" + f + "</li>";
        })
        .join("") +
      "</ul></details>" +
      '<details class="block"><summary>Metrics</summary><div class="scroll"><table><thead><tr><th>Metric</th><th>Formula</th><th>Unit</th><th>Better</th><th>Target</th><th>Latest</th><th>Used by</th></tr></thead><tbody>' +
      mt +
      "</tbody></table></div></details>" +
      '<details class="block"><summary>Roles and escalation</summary><div class="scroll"><table><thead><tr><th>Role</th><th>Escalates to</th><th>May spawn</th><th>Rungs</th></tr></thead><tbody>' +
      rt +
      "</tbody></table></div>" +
      (w.vetoes.length
        ? "<p>Vetoes no change may break:</p><ul>" +
          w.vetoes
            .map(function (v) {
              return "<li>" + esc(v) + "</li>";
            })
            .join("") +
          "</ul>"
        : "") +
      "</details></div>"
    );
  }

  // ------------------------------------------------------------------ build progress (tracker)
  function unitGraph(D, units, sel, hrefOf, opt, faded) {
    var by = {};
    D.build.units.forEach(function (u) {
      by[u.id] = u;
    });
    var ids = units.map(function (u) {
        return u.id;
      }),
      extra = [];
    if (faded)
      units.forEach(function (u) {
        u.dep.forEach(function (d) {
          if (ids.indexOf(d) < 0 && extra.indexOf(d) < 0 && by[d])
            extra.push(d);
        });
      });
    var all = ids.concat(extra);
    var nodes = all.map(function (id) {
      return { id: id, layer: by[id].w - 1 };
    });
    var edges = [],
      deps = {};
    all.forEach(function (id) {
      deps[id] = by[id].dep.filter(function (d) {
        return all.indexOf(d) >= 0;
      });
    });
    function reaches(a, b, seen) {
      // a needs b, directly or through other units
      seen = seen || {};
      return deps[a].some(function (d) {
        if (d === b) return true;
        if (seen[d]) return false;
        seen[d] = 1;
        return reaches(d, b, seen);
      });
    }
    all.forEach(function (id) {
      deps[id].forEach(function (d) {
        var implied = deps[id].some(function (o) {
          return o !== d && reaches(o, d);
        });
        if (!implied) edges.push({ from: d, to: id });
      });
    });
    var narrow = opt.width && opt.width < 760,
      dir = narrow ? "TB" : "LR";
    var lay = G.layered(nodes, edges, {
      dir: dir,
      gapMain: narrow ? 150 : 200,
      gapCross: narrow ? 160 : 118,
      pad: 80,
    });
    var P = lay.pos,
      body = "",
      maxAcc = 1;
    all.forEach(function (id) {
      maxAcc = Math.max(maxAcc, (by[id].acc || []).length);
    });
    var waves = 0;
    all.forEach(function (id) {
      waves = Math.max(waves, by[id].w);
    });
    for (var k = 1; k <= waves; k++) {
      var inW = all.filter(function (id) {
          return by[id].w === k;
        }),
        any = inW[0];
      if (!any) continue;
      var dn = inW.filter(function (id) {
        return by[id].st === "done";
      }).length;
      var lab =
        "Wave " +
        k +
        ' <tspan class="num">' +
        dn +
        " of " +
        inW.length +
        " done</tspan>";
      if (dir === "LR")
        body +=
          '<rect class="lane" x="' +
          (P[any].x - 92) +
          '" y="44" width="184" height="' +
          (lay.h - 20) +
          '" rx="14" style="opacity:' +
          (k % 2 ? 1 : 0.5) +
          '"/><text class="wave" text-anchor="middle" x="' +
          P[any].x +
          '" y="30">' +
          lab +
          "</text>";
      else
        body +=
          '<text class="wave" x="12" y="' +
          (P[any].y - 34) +
          '">' +
          lab +
          "</text>";
    }
    edges.forEach(function (e) {
      var p = G.edgePath(P[e.from], P[e.to], dir, 24, 24);
      body += G.edge({
        id: e.from + ">" + e.to,
        from: e.from,
        to: e.to,
        d: p.d,
        mid: p.mid,
        kind: "dep",
        faded: extra.indexOf(e.from) >= 0,
      });
    });
    all.forEach(function (id) {
      var u = by[id],
        na = (u.acc || []).length;
      body += G.node({
        id: id,
        x: P[id].x,
        y: P[id].y,
        r: 22,
        seg: segOfUnit(D, u),
        st: unitSt(u),
        label: id,
        labelLines: [id].concat(short2(u.name)),
        faded: extra.indexOf(id) >= 0,
        cls: sel === id ? "sel" : "",
        href: hrefOf(id),
        maxw: 170,
        heat: 0.12 + (0.45 * na) / maxAcc,
        badge: na || null,
        title:
          id +
          " " +
          u.name +
          ": " +
          (u.state || u.st) +
          (u.note && u.note !== u.state ? ", " + u.note : "") +
          ". " +
          (u.what || ""),
      });
    });
    return G.svg(lay.w + 120, lay.h + 80, body, "Build units by wave");
  }
  function unitSt(u) {
    return ["active", "done", "gate", "failed"].indexOf(u.st) >= 0
      ? u.st
      : "queued";
  }
  var SRC = {
    plan: "the work package (status-units.json, agent plans, run log)",
    gh: "GitHub",
    ingest: "a client report (ingest)",
  };
  function short2(s) {
    var l = G.wrap(s, 18);
    if (l.length > 2) {
      l = l.slice(0, 2);
      l[1] = l[1].replace(/\W*$/, "") + "…";
    }
    return l;
  }
  function unitPanel(D, id, close) {
    var u = D.build.units.filter(function (x) {
      return x.id === id;
    })[0];
    if (!u) return null;
    var pr = u.pr ? D.build.prs[String(u.pr)] : null;
    var prTxt = u.pr
      ? "#" +
        u.pr +
        (pr
          ? ", " + (pr.draft ? "draft" : "ready") + ", checks " + pr.ci
          : ", not open (merged or closed)")
      : "none";
    var stc = unitSt(u),
      stTxt = u.state || (u.st === "active" ? "being built" : u.st);
    var since = u.state_at
      ? new Date(u.state_at * 1000)
          .toISOString()
          .slice(0, 16)
          .replace("T", " ") + " UTC"
      : null;
    return panel({
      title: u.id + " " + u.name,
      close: close,
      kind: "build unit, wave " + u.w,
      st: [stc, stTxt],
      goal: goal(D, "unit", u),
      secs: {
        what: dl([
          ["Target", esc(u.tgt)],
          [
            "State",
            esc(stTxt) +
              (noteOf(u.state, u.note) ? ", " + esc(u.note) : "") +
              (u.conflict
                ? '<br><span class="warn">' + esc(u.conflict) + "</span>"
                : ""),
          ],
          [
            "State from",
            esc(SRC[u.state_src] || u.state_src || "") +
              (since ? ", " + esc(since) : ""),
          ],
          ["Agent", u.agent ? esc(u.agent) : null],
          ["Pull request", esc(prTxt)],
          ["Branch", u.branch ? code(u.branch) : null],
          ["Defined in", code(u.src)],
        ]),
        inputs: dl([
          [
            "Needs",
            u.dep.length
              ? u.dep
                  .map(function (d) {
                    return (
                      '<a href="#/build/' + enc(d) + '">' + esc(d) + "</a>"
                    );
                  })
                  .join(", ")
              : "nothing",
          ],
        ]),
        outputs: dl([
          [
            "Builds",
            u.items.length
              ? u.items
                  .map(function (i) {
                    return (
                      '<a href="' +
                      itemHref(D, i) +
                      '">' +
                      esc(D.org.items[i] ? D.org.items[i].name : i) +
                      "</a>"
                    );
                  })
                  .join(", ")
              : null,
          ],
        ]),
        checks:
          u.acc && u.acc.length
            ? '<ol class="rules">' +
              u.acc
                .map(function (a) {
                  return "<li>" + esc(a) + "</li>";
                })
                .join("") +
              "</ol>"
            : "",
        history:
          (u.followup
            ? "<p>" + esc(u.followup.label + ": " + u.followup.text) + "</p>"
            : "") +
          ((u.findings || []).length
            ? "<p>Findings:</p><ul>" +
              u.findings
                .map(function (f) {
                  return "<li>" + code("work-package/findings/" + f) + "</li>";
                })
                .join("") +
              "</ul>"
            : ""),
      },
    });
  }
  function build(D, r, opt) {
    var U = D.build.units,
      done = U.filter(function (u) {
        return u.st === "done";
      }).length,
      act = U.filter(function (u) {
        return u.st === "active";
      });
    var C = D.org.critical,
      own = C.owner_units || [],
      bad = C.failing.length + (C.failing_units || []).length,
      I = D.build.ingest || {};
    function uli(u) {
      return (
        '<li><a href="#/build/' +
        enc(u.id || u.unit) +
        '">' +
        esc((u.id || u.unit) + " " + u.name) +
        "</a> " +
        esc(u.state || "") +
        "</li>"
      );
    }
    var ci = Object.keys(C.ci)
      .map(function (k) {
        return C.ci[k] + " " + k;
      })
      .join(", ");
    var panelHtml = r.sel ? unitPanel(D, r.sel, "#/build") : null;
    if (r.sel && !panelHtml) return notfound(r);
    var strip0 =
      '<div class="band" role="region" aria-label="Build state"><section class="slot pulse-slot"><h2>Units done</h2>' +
      ringStat(done, U.length, done + " of " + U.length + " units done") +
      '<div class="sparkbox"><p><b data-count="' +
      done +
      '" class="num">' +
      done +
      "</b> of " +
      U.length +
      " units</p></div></section>" +
      '<section class="slot s-build' +
      (act.length ? " on" : "") +
      '"><h2>Being built <span data-count="' +
      act.length +
      '" class="n">' +
      act.length +
      "</span></h2>" +
      (act.length
        ? "<ul>" + act.map(uli).join("") + "</ul>"
        : '<p class="empty">Nothing is being built.</p>') +
      "</section>" +
      '<section class="slot s-owner' +
      (own.length ? " on" : "") +
      '"><h2>Units that need you <span data-count="' +
      own.length +
      '" class="n">' +
      own.length +
      "</span></h2>" +
      (own.length
        ? "<ul>" + own.map(uli).join("") + "</ul>"
        : '<p class="empty">No unit waits for you.</p>') +
      "</section>" +
      '<section class="slot s-fail' +
      (bad ? " on" : "") +
      '"><h2>Failing <span data-count="' +
      bad +
      '" class="n">' +
      bad +
      "</span></h2>" +
      (bad
        ? "<ul>" +
          C.failing
            .map(function (p) {
              return "<li>Pull request #" + p.n + " " + esc(p.title) + "</li>";
            })
            .join("") +
          (C.failing_units || []).map(uli).join("") +
          "</ul>"
        : '<p class="empty">' +
          (C.gh_error ? "Unknown: gh failed." : "None.") +
          "</p>") +
      '<p class="empty">' +
      (C.open_prs || 0) +
      " open pull request" +
      (C.open_prs === 1 ? "" : "s") +
      (ci ? ", checks " + esc(ci) : "") +
      ".</p></section></div>" +
      (I.broken
        ? '<p class="warn">Ingest log ' +
          code(I.path) +
          ": " +
          esc(I.broken) +
          ", " +
          I.ignored +
          " line" +
          (I.ignored === 1 ? "" : "s") +
          " ignored; new reports are refused until the file is moved aside.</p>"
        : "");
    return (
      head(
        [
          ["Organization", "#/"],
          ["Build progress", ""],
        ],
        "Build progress",
        done +
          " of " +
          U.length +
          " units done" +
          (act.length ? ", " + act.length + " being built" : "") +
          ". The latest state of each unit, from client reports (" +
          (I.events || 0) +
          " in the ingest log), GitHub and the work package, the newest first.",
      ) +
      strip0 +
      stage(
        unitGraph(
          D,
          U,
          r.sel,
          function (id) {
            return "#/build/" + enc(id);
          },
          opt,
          false,
        ),
        panelHtml,
        "Each column is a wave; a unit starts when every unit it needs is done. Color is the segment a unit builds for; tint and badge grow with its acceptance items. Arrows implied by a longer path are left out.",
        legend(LEG_STATE),
      )
    );
  }
  function component(D, r, opt) {
    var it = D.org.items[r.id];
    if (!it || it.kind !== "component") return notfound(r);
    var units = D.build.units.filter(function (u) {
      return it.units.indexOf(u.id) >= 0;
    });
    var close = "#/c/" + enc(it.id),
      panelHtml = r.sel ? unitPanel(D, r.sel, close) : null;
    if (r.sel && !panelHtml) return notfound(r);
    var files = it.files
      .map(function (f) {
        return (
          "<tr><td>" +
          code(f.path) +
          "</td><td>" +
          esc(f.size || "not in this tree") +
          "</td></tr>"
        );
      })
      .join("");
    return (
      head(
        [
          ["Organization", "#/"],
          ["Platform", "#/s/platform", "platform"],
          [it.name, "", "platform"],
        ],
        it.name,
        units.length + " build unit" + (units.length === 1 ? "" : "s") + ".",
        null,
        { goal: goal(D, "component", it), seg: "platform" },
      ) +
      stage(
        unitGraph(
          D,
          units,
          r.sel,
          function (id) {
            return close + "/u/" + enc(id);
          },
          opt,
          true,
        ),
        panelHtml,
        "The units that build this component; faded ones belong to other parts and are needed first.",
        legend(LEG_STATE),
        "platform",
      ) +
      '<details class="block"><summary>Files in the tree</summary><div class="scroll"><table><thead><tr><th>Path</th><th>Size</th></tr></thead><tbody>' +
      files +
      "</tbody></table></div></details>"
    );
  }

  // ------------------------------------------------------------------ process language
  function language(D, r, opt) {
    var L = D.language;
    var groups = [
      ["work", "Work"],
      ["wait", "Wait"],
      ["signal", "Signal"],
      ["flow", "Flow"],
    ];
    var body = "",
      y = 50,
      maxW = 0,
      maxC = 1;
    L.kinds.forEach(function (k) {
      maxC = Math.max(maxC, k.count);
    });
    groups.forEach(function (g) {
      var ks = L.kinds.filter(function (k) {
        return k.group === g[0];
      });
      body +=
        '<text class="wave" x="24" y="' + y + '">' + esc(g[1]) + "</text>";
      ks.forEach(function (k, i) {
        var x = 150 + i * 170;
        var st =
          {
            step: "model",
            call: "code",
            set: "code",
            gate: "human",
            listen: "event",
            wait: "event",
            emit: "event",
            raise: "escalated",
          }[k.kind] || "code";
        var kk =
          {
            step: "step",
            call: "call",
            set: "step",
            gate: "gate",
            listen: "event",
            wait: "event",
            emit: "event",
            raise: "raise",
          }[k.kind] || "step";
        var sh =
          {
            gate: "hex",
            listen: "tag",
            wait: "tag",
            emit: "tag",
            set: "square",
            switch: "square",
          }[k.kind] || null;
        body += G.node({
          id: "kind:" + k.kind,
          x: x,
          y: y - 6,
          r: Math.round(12 + 10 * Math.sqrt(k.count / maxC)),
          st: k.count ? st : "queued",
          kind: kk,
          shape: sh,
          lv: 2,
          heat: k.count ? 0.12 + (0.4 * k.count) / maxC : 0,
          label: k.label,
          sub: k.count ? k.count + " in use" : "not used yet",
          maxw: 160,
          title:
            k.label +
            ": " +
            (k.count
              ? k.count + " in the workflows"
              : "in the grammar, not used yet"),
        });
        maxW = Math.max(maxW, x + 100);
      });
      y += 130;
    });
    var kindsSvg = G.svg(
      Math.max(maxW, 700),
      y - 20,
      body,
      "Node kinds of the grammar",
    );
    var cb = "",
      cy = 40;
    L.connections.forEach(function (c) {
      var dashed = c.id === "then" || c.id === "case";
      cb +=
        '<g class="edge k-' +
        (c.id === "event" ? "event" : c.id === "loop" ? "loop" : "flow") +
        (dashed ? " dashed" : "") +
        '"><path class="ep" d="M40,' +
        cy +
        ' H180" marker-end="url(#arrow)"/></g>' +
        '<text class="lab" x="200" y="' +
        (cy + 5) +
        '">' +
        esc(c.label) +
        '</text><text class="sub" x="330" y="' +
        (cy + 5) +
        '">' +
        esc(c.about + ", " + c.count + " in use") +
        "</text>";
      cy += 46;
    });
    var connSvg = G.svg(760, cy, cb, "Connection kinds");
    var checks = L.checks
      .map(function (c) {
        return (
          "<li>" +
          code(c.id) +
          ", " +
          esc(c.cls) +
          (c.used_by.length
            ? ", on " + c.used_by.map(code).join(", ")
            : ", not used") +
          (c.reads
            ? '<br><span class="muted">reads ' + c.reads + "</span>"
            : "") +
          "</li>"
        );
      })
      .join("");
    var secs = L.sections
      .map(function (s) {
        return (
          '<details class="block doc" id="sec-' +
          esc(s.id) +
          '"' +
          (r.sel === s.id ? " open" : "") +
          "><summary>" +
          esc(s.title) +
          '</summary><div class="legacy">' +
          s.html +
          "</div></details>"
        );
      })
      .join("");
    return (
      head(
        [
          ["Organization", "#/"],
          ["Process language", ""],
        ],
        "Process language",
        "The grammar every workflow is written in: a closed set of node kinds and connections. The counts come from the workflow files in the org root.",
      ) +
      '<section class="block"><h2>Node kinds</h2>' +
      stage(
        kindsSvg,
        null,
        "Shape and color name the kind; size grows with how often the workflows use it. A dashed outline is a kind no workflow uses yet.",
        null,
      ) +
      "</section>" +
      '<section class="block"><h2>Connections</h2>' +
      stage(connSvg, null, null) +
      "</section>" +
      '<details class="block"><summary>Checks (' +
      L.checks.length +
      ')</summary><ul class="plain">' +
      checks +
      "</ul></details>" +
      '<h2 class="doc-h">Reference</h2><p class="lead">The longer explanation, from the earlier process-language page.</p>' +
      secs
    );
  }

  // ------------------------------------------------------------------ decisions
  function decisions(D, r) {
    var items = D.decisions.items;
    function li(d) {
      var st = d.open
        ? "gate"
        : d.state === "done" || d.state === "resolved"
          ? "done"
          : d.state === "running"
            ? "active"
            : "queued";
      return (
        '<li id="d-' +
        esc(d.id) +
        '" class="dec' +
        (r.sel === d.id ? " sel" : "") +
        '"><svg width="26" height="26" viewBox="-13 -13 26 26" aria-hidden="true">' +
        G.node({ id: "d", x: 0, y: 0, r: 10, st: st, label: "" }).replace(
          /<title>.*?<\/title>/,
          "",
        ) +
        "</svg><div><h3>" +
        esc(d.title) +
        " " +
        chip(st, d.state) +
        "</h3><p>" +
        esc(d.text) +
        '</p><p class="src">Source: ' +
        code("work-package/" + d.src) +
        (d.found ? "" : ", source text not found, may be stale") +
        "</p></div></li>"
      );
    }
    var open = items.filter(function (d) {
        return d.open;
      }),
      rest = items.filter(function (d) {
        return !d.open;
      });
    var log = D.decisions.log
      .map(function (l) {
        return (
          '<li><span class="date">' +
          esc(l.date) +
          "</span> " +
          l.html +
          "</li>"
        );
      })
      .join("");
    return (
      head(
        [
          ["Organization", "#/"],
          ["Decisions and open items", ""],
        ],
        "Decisions and open items",
        open.length + " open for you, " + rest.length + " other items.",
      ) +
      '<section class="block"><h2>Open for you</h2>' +
      (open.length
        ? '<ul class="decs">' + open.map(li).join("") + "</ul>"
        : '<p class="empty">Nothing is open for you.</p>') +
      "</section>" +
      '<details class="block"><summary>Other items (' +
      rest.length +
      ')</summary><ul class="decs">' +
      rest.map(li).join("") +
      "</ul></details>" +
      '<details class="block"><summary>Your decisions so far</summary><div class="doc">' +
      D.decisions.owner_html +
      "</div></details>" +
      '<details class="block"><summary>Orchestrator run log, newest first (' +
      D.decisions.log.length +
      " of " +
      D.decisions.log_rows +
      ')</summary><ol class="log">' +
      log +
      "</ol></details>"
    );
  }

  function notfound(r) {
    return head(
      [
        ["Organization", "#/"],
        ["Not found", ""],
      ],
      "Nothing here",
      "No view matches <code>#" +
        esc(r.raw || "") +
        '</code>. Go back to the <a href="#/">organization</a>.',
    );
  }

  function render(route, D, opt) {
    opt = opt || {};
    opt.now = opt.now || (D.live && D.live.at) || 0;
    switch (route.view) {
      case "home":
        return home(D, opt);
      case "segment":
        return segment(D, route, opt);
      case "workflow":
        return workflow(D, route, opt);
      case "component":
        return component(D, route, opt);
      case "build":
        return build(D, route, opt);
      case "language":
        return language(D, route, opt);
      case "decisions":
        return decisions(D, route, opt);
      default:
        return notfound(route);
    }
  }
  function title(route, D) {
    return (
      {
        home: "Organization",
        segment: route.seg && segName(D, route.seg),
        workflow: route.wf,
        component:
          route.id && D.org.items[route.id] ? D.org.items[route.id].name : "",
        build: "Build progress",
        language: "Process language",
        decisions: "Decisions",
      }[route.view] || "Not found"
    );
  }

  // ------------------------------------------------------------------ jump palette index: every place the site can show
  function searchIndex(D) {
    var out = [
      ["Organization", "home", "#/", null],
      ["Build progress", "page", "#/build", null],
      ["Process language", "page", "#/language", null],
      ["Decisions and open items", "page", "#/decisions", null],
    ];
    D.org.segments.forEach(function (s) {
      out.push([s.name, "segment", "#/s/" + enc(s.id), s.id]);
    });
    Object.keys(D.org.items).forEach(function (i) {
      var it = D.org.items[i];
      if (it.kind === "component")
        out.push([it.name, "component", "#/c/" + enc(i), it.seg]);
    });
    Object.keys(D.workflows).forEach(function (wid) {
      var w = D.workflows[wid],
        sg = segOf(D, wid);
      out.push([wid, "workflow, " + segName(D, sg), wfHref(wid), sg]);
      out.push([
        wid + " operations",
        "workflow operations",
        wfHref(wid, { ops: true }),
        sg,
      ]);
      walk(w.tree).forEach(function (n) {
        out.push([
          n.name,
          (n.children || n.branches ? "group" : n.label) +
            " in " +
            wid +
            ", " +
            n.key,
          wfHref(wid, { sel: n.key }),
          sg,
        ]);
      });
    });
    D.build.units.forEach(function (u) {
      out.push([
        u.id + " " + u.name,
        "build unit, wave " + u.w + ", " + (u.state || u.st),
        "#/build/" + enc(u.id),
        segOfUnit(D, u),
      ]);
    });
    D.decisions.items.forEach(function (d) {
      out.push([
        d.title,
        "decision, " + d.state,
        "#/decisions/" + enc(d.id),
        null,
      ]);
    });
    D.language.sections.forEach(function (s) {
      out.push([s.title, "process language", "#/language/" + enc(s.id), null]);
    });
    runs(D).forEach(function (r) {
      (r.workflows || [r.workflow]).forEach(function (wf) {
        if (D.workflows[wf])
          out.push([
            "Run " + String(r.run_id || r.id).slice(0, 8) + " of " + wf,
            "run, " +
              (r.status === "running"
                ? "running"
                : "ended " + (r.end_status || "")),
            wfHref(wf, { run: r.id }),
            segOf(D, wf),
          ]);
      });
    });
    return out.map(function (x) {
      return { label: x[0], sub: x[1], href: x[2], seg: x[3] };
    });
  }
  // the parent of a route, for Escape and the zoom-out direction
  function parent(route, D) {
    if (route.view === "workflow") {
      if (route.sel)
        return wfHref(route.wf, { run: route.run, ops: route.ops });
      if (route.ops) return wfHref(route.wf, { run: route.run });
      return segOf(D, route.wf) ? "#/s/" + enc(segOf(D, route.wf)) : "#/";
    }
    if (route.view === "component")
      return route.sel ? "#/c/" + enc(route.id) : "#/s/platform";
    if (route.view === "segment") return "#/";
    if (["build", "language", "decisions"].indexOf(route.view) >= 0)
      return route.sel ? "#/" + route.view : "#/";
    return null;
  }
  function depth(route) {
    return (
      {
        home: 0,
        segment: 1,
        build: 1,
        language: 1,
        decisions: 1,
        component: 2,
        workflow: 2,
        notfound: 0,
      }[route.view] +
      (route.ops ? 1 : 0) +
      (route.sel ? 1 : 0)
    );
  }

  // ------------------------------------------------------------------ live state of graph nodes in a view
  function liveStates(route, D, now) {
    var out = {};
    var act = running(D);
    if (route.view === "home") {
      D.org.segments.forEach(function (s) {
        var rs = act.filter(function (r) {
          return r.workflows.concat([r.workflow]).some(function (wf) {
            return segOf(D, wf) === s.id;
          });
        });
        if (rs.length)
          out[s.id] = {
            st: rs.some(function (r) {
              return (r.current || []).some(function (c) {
                return isGate(D, c.wf, c.rel);
              });
            })
              ? "gate"
              : "active",
            sub: rs[0].workflow + ": " + stepLine(rs[0], now),
            chg: changeLine(rs[0]),
          };
      });
    } else if (route.view === "segment") {
      var sg = D.org.seg_graphs[route.seg];
      if (sg)
        sg.nodes.forEach(function (n) {
          var rs = act.filter(function (r) {
            return (
              (r.workflows || []).indexOf(n.id) >= 0 || r.workflow === n.id
            );
          });
          if (rs.length)
            out[n.id] = {
              st: "active",
              sub: stepLine(rs[0], now),
              chg: changeLine(rs[0]),
            };
        });
    } else if (route.view === "workflow") {
      var w = D.workflows[route.wf],
        run = w && pickRun(D, route.wf, route.run);
      if (run) {
        var tasks = tasksFor(run, w.id);
        walk(w.tree).forEach(function (n) {
          if (n.children || n.branches) return;
          var t = tasks[n.key],
            st = taskState(t, n),
            sub = "";
          if (t && t.state === "running") {
            var c = (run.current || []).filter(function (x) {
              return x.rel === n.key && x.wf === w.id;
            })[0];
            sub = c
              ? dur(now - c.since) + (t.usd ? ", " + usd(t.usd) : "")
              : "";
          } else if (t && t.starts > 1)
            sub = t.starts + " rounds" + (t.usd ? ", " + usd(t.usd) : "");
          else if (t && t.usd) sub = usd(t.usd);
          out[(route.ops ? "step:" : "") + n.key] = { st: st, sub: sub };
        });
        if (route.ops)
          opsModel(D, w).rows.forEach(function (row) {
            var t = tasks[row.n.key];
            row.acc.forEach(function (o) {
              var ast = o.st;
              if (t && o.a.type === "check" && t.checks && o.a.id in t.checks)
                ast = t.checks[o.a.id] === true ? "done" : "failed";
              if (
                t &&
                o.a.type === "rubric" &&
                t.judges &&
                String(o.idx) in t.judges
              )
                ast =
                  t.judges[String(o.idx)] === "pass"
                    ? "done"
                    : t.judges[String(o.idx)] === "fail"
                      ? "failed"
                      : "queued";
              out[o.id] = { st: ast };
            });
          });
      }
    }
    return out;
  }

  // ------------------------------------------------------------------ feedback: what to animate for one ledger event
  function feedback(route, D, ev, run) {
    var tok = ev && ev.token,
      acts = [];
    if (!run) return acts;
    var wf = (tok && tok.wf) || run.workflow;
    if (route.view === "home") {
      var seg = segOf(D, wf);
      if (!seg) return acts;
      if (tok && (tok.type === "trigger" || tok.type === "gate"))
        acts.push({ edge: "owner>" + seg });
      if (
        tok &&
        (tok.type === "emit" || tok.type === "event" || tok.type === "feed")
      )
        acts.push({ events: tok.event });
      acts.push({
        node: seg,
        cls: tok && tok.type === "accept" && !tok.ok ? "bad" : "",
      });
    } else if (route.view === "segment") {
      var sg = D.org.seg_graphs[route.seg];
      if (!sg) return acts;
      var w = D.workflows[wf];
      if (tok && tok.type === "trigger" && w && w.start)
        acts.push({ edge: "start:" + w.start + ">" + wf });
      if (tok && tok.type === "call")
        sg.edges.forEach(function (e) {
          if (e.to === tok.wf && e.kind === "call")
            acts.push({ edge: e.from + ">" + e.to });
        });
      if (tok && (tok.type === "emit" || tok.type === "event"))
        acts.push({ events: tok.event });
      acts.push({ node: wf });
    } else if (route.view === "workflow" && route.wf === wf) {
      var shown = pickRun(D, route.wf, route.run);
      if (!shown || shown.id !== run.id || !tok || !tok.rel) return acts;
      var pre = route.ops ? "step:" : "";
      if (tok.type === "start") acts.push({ edge: "seq:" + tok.rel });
      if (tok.type === "rework") {
        var parent = tok.rel.split("/").slice(0, -1).join("/");
        if (parent) acts.push({ edge: "loop:" + parent });
        acts.push({ edge: "seq:" + tok.rel });
      }
      if (
        (tok.type === "accept" ||
          tok.type === "check" ||
          tok.type === "judge") &&
        route.ops
      )
        acts.push({ prefix: "acc:" + tok.rel + ":" });
      acts.push({
        node: pre + tok.rel,
        cls:
          tok.type === "accept" || tok.type === "check" || tok.type === "judge"
            ? tok.ok
              ? "good"
              : "bad"
            : "",
      });
    }
    return acts;
  }

  function routes(D) {
    var out = ["#/", "#/build", "#/language", "#/decisions"];
    D.org.segments.forEach(function (s) {
      out.push("#/s/" + enc(s.id));
    });
    Object.keys(D.workflows).forEach(function (w) {
      out.push(wfHref(w));
      out.push(wfHref(w, { ops: true }));
    });
    Object.keys(D.org.items).forEach(function (i) {
      if (D.org.items[i].kind === "component") out.push("#/c/" + enc(i));
    });
    return out;
  }

  var api = {
    critical: critical,
    runSummary: runSummary,
    parse: parse,
    render: render,
    title: title,
    liveStates: liveStates,
    feedback: feedback,
    routes: routes,
    wfHref: wfHref,
    dur: dur,
    usd: usd,
    walk: walk,
    pickRun: pickRun,
    goal: goal,
    searchIndex: searchIndex,
    parent: parent,
    depth: depth,
    findNode: findNode,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.V = api;
})(this);
