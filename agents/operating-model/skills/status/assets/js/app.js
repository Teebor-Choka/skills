/* The page: routing, data loading, live feed, partial updates and the moving tokens. */
(function () {
  "use strict";
  var D = window.ORG_DATA,
    V = window.V,
    G = window.G;
  var main = document.getElementById("main");
  var LIVE = location.protocol === "http:" || location.protocol === "https:";
  var reduce =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  var route = null,
    lastView = null,
    lastSel = null,
    pending = false,
    feed = "off",
    refreshErr = null,
    lastRender = 0;
  // client state that survives every re-render: folded groups per workflow, legend filters, the last selected node
  var folded = {},
    filters = [],
    lastClick = null,
    lastDepth = 0;
  var STILL = /[?&]nostream\b/.test(location.search); // headless screenshots: no entrance motion, final values at once
  function calm() {
    return STILL || !!(reduce && reduce.matches);
  }
  document.documentElement.classList.toggle("still", STILL);
  var FILES = ["org", "workflows", "build", "decisions", "language", "meta"];

  function now() {
    return Date.now() / 1000;
  }
  function busy() {
    var s = window.getSelection && String(window.getSelection());
    var a = document.activeElement;
    return !!s || !!(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
  }

  // ---------------------------------------------------------------- render
  function render(fromRoute) {
    route = V.parse(location.hash);
    var openDetails = [].map.call(
      main.querySelectorAll("details[open] > summary"),
      function (s) {
        return s.textContent;
      },
    );
    var sx = window.scrollX,
      sy = window.scrollY;
    var sb = main.querySelector(".canvas .sb"),
      sl = sb ? [sb.scrollLeft, sb.scrollTop] : null;
    var key0 =
      route.view +
      "|" +
      (route.wf || route.seg || route.id || "") +
      "|" +
      (route.ops ? 1 : 0);
    if (fromRoute && key0 !== (lastView || "").split("|").slice(0, 3).join("|"))
      filters = [];
    main.innerHTML = V.render(route, D, {
      width: main.clientWidth - 40,
      now: now(),
      collapsed: route.wf ? folded[route.wf] || {} : {},
    });
    lastRender = Date.now();
    document.title = V.title(route, D) + ", organization";
    if (!fromRoute) {
      [].forEach.call(main.querySelectorAll("details > summary"), function (s) {
        if (openDetails.indexOf(s.textContent) >= 0) s.parentNode.open = true;
      });
      window.scrollTo(sx, sy);
      var nb = main.querySelector(".canvas .sb");
      if (nb && sl) {
        nb.scrollLeft = sl[0];
        nb.scrollTop = sl[1];
      }
    } else {
      var viewKey =
        route.view +
        "|" +
        (route.wf || route.seg || route.id || "") +
        "|" +
        (route.ops ? 1 : 0) +
        "|" +
        (route.run || "");
      if (viewKey !== lastView) {
        var h = main.querySelector("h1");
        if (h) h.focus({ preventScroll: true });
        window.scrollTo(0, 0);
        var d = V.depth(route);
        if (lastView !== null)
          drill(d > lastDepth ? "in" : d < lastDepth ? "out" : null);
        countUp();
      } else if (route.sel && route.sel !== lastSel) {
        var ph = main.querySelector(".panel h2");
        if (ph) {
          ph.setAttribute("tabindex", "-1");
          ph.focus({ preventScroll: true });
        }
      }
      lastView = viewKey;
      lastSel = route.sel;
      lastDepth = V.depth(route);
      if (route.view === "decisions" && route.sel) {
        var el = document.getElementById("d-" + route.sel);
        if (el) el.scrollIntoView({ block: "center" });
      }
      if (route.view === "language" && route.sel) {
        var se = document.getElementById("sec-" + route.sel);
        if (se) se.scrollIntoView();
      }
      var sel = main.querySelector(".node.sel");
      if (sel && sel.scrollIntoView)
        sel.scrollIntoView({ block: "nearest", inline: "nearest" });
      var osb =
        route.ops &&
        route.sel &&
        main.querySelector(".stage.has-panel .canvas .sb");
      if (osb && osb.scrollWidth > osb.clientWidth) osb.scrollLeft = 380; // with the panel open, show the spine, checks and judges, not the inputs column
    }
    applyLive();
    applyFilters();
    sidebar();
  }
  function rerenderSoon() {
    if (busy()) {
      pending = true;
      return;
    }
    pending = false;
    render(false);
  }

  // ---------------------------------------------------------------- live layer on the nodes
  function applyLive() {
    var states = V.liveStates(route, D, now());
    [].forEach.call(
      main.querySelectorAll("svg.graph .node[data-node]"),
      function (g) {
        if (!g.hasAttribute("data-st0")) {
          var m = g.getAttribute("class").match(/\bst-([a-z]+)/);
          g.setAttribute("data-st0", m ? m[1] : "queued");
        }
        var id = g.getAttribute("data-node"),
          s = states[id];
        var st = s && s.st ? s.st : g.getAttribute("data-st0");
        g.setAttribute(
          "class",
          g.getAttribute("class").replace(/\bst-[a-z]+/, "st-" + st),
        );
        var t = g.querySelector("[data-livesub]");
        if (t) t.textContent = s && s.sub ? s.sub : "";
        var c = g.querySelector("[data-livechg]");
        if (c) c.textContent = s && s.chg ? s.chg : "";
      },
    );
  }
  function anyRunning() {
    return (D.live.runs || []).some(function (r) {
      return r.status === "running";
    });
  }

  // ---------------------------------------------------------------- sidebar
  function sidebar() {
    var K = V.critical(D, now()),
      nb = K.building.length,
      no = K.owner.length,
      nf = K.failing.length;
    set(
      "sb-build",
      nb ? nb + " running or building" : "Nothing building",
      nb ? "active" : "",
    );
    set(
      "sb-owner",
      no ? no + " need" + (no === 1 ? "s" : "") + " you" : "Nothing for you",
      no ? "gate" : "",
    );
    set(
      "sb-fail",
      K.unknown
        ? "Failing: unknown, gh failed"
        : nf
          ? nf + " failing"
          : "Nothing failing",
      K.unknown ? "gate" : nf ? "failed" : "",
    );
    [].forEach.call(document.querySelectorAll("[data-nav]"), function (a) {
      var on =
        a.getAttribute("data-nav") === route.view ||
        (a.getAttribute("data-nav") === "home" &&
          ["segment", "workflow", "component"].indexOf(route.view) >= 0);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
      if (on && a.closest("details")) a.closest("details").open = true;
    });
    var m = D.meta,
      txt;
    if (!LIVE)
      txt =
        "Read-only copy from " +
        m.generated_text +
        ". For live data start scripts/serve.py of the status skill and open http://127.0.0.1:8765/.";
    else
      txt =
        "Data from " +
        m.generated_text +
        ". " +
        (feed === "on"
          ? "Live feed connected."
          : feed === "retry"
            ? "Live feed reconnecting."
            : "Live feed off.") +
        (refreshErr ? " Refresh failed: " + refreshErr : "");
    if (m.gh !== "live") txt += " Pull requests: gh " + m.gh + ".";
    if (m.simulated) txt += " Simulated states.";
    document.getElementById("sb-data").textContent = txt;
    document.getElementById("sb-refresh").hidden = !LIVE;
  }
  function set(id, text, st) {
    var a = document.getElementById(id);
    a.querySelector(".t").textContent = text;
    a.className = st ? "st-" + st : "";
  }

  // ---------------------------------------------------------------- data
  function getJSON(u) {
    return fetch(u, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(u + ": HTTP " + r.status);
      return r.json();
    });
  }
  function loadAll() {
    return Promise.all(
      FILES.map(function (f) {
        return getJSON("data/" + f + ".json");
      }).concat([getJSON("api/live")]),
    ).then(function (xs) {
      var nd = {};
      FILES.forEach(function (f, i) {
        nd[f] = xs[i];
      });
      nd.live = xs[FILES.length];
      D = nd;
    });
  }
  function refresh(force) {
    if (!LIVE || (document.hidden && !force)) return;
    getJSON("api/refresh")
      .then(function (meta) {
        refreshErr = meta.error || null;
        if (meta.hash && meta.hash !== D.meta.hash)
          return loadAll().then(rerenderSoon);
        D.meta = meta;
        sidebar();
      })
      .catch(function (e) {
        refreshErr = String(e.message || e);
        sidebar();
      });
  }

  // ---------------------------------------------------------------- live feed (server-sent events)
  function connect() {
    if (!LIVE || !window.EventSource || /[?&]nostream\b/.test(location.search))
      return; // nostream: for headless screenshots, which wait for the network to go idle
    var es = new EventSource("api/events");
    es.onopen = function () {
      feed = "on";
      sidebar();
    };
    es.onerror = function () {
      feed = "retry";
      sidebar();
    };
    es.onmessage = function (m) {
      var msg;
      try {
        msg = JSON.parse(m.data);
      } catch (e) {
        return;
      }
      if (msg.build) {
        if (msg.build.hash !== D.meta.hash)
          loadAll()
            .then(rerenderSoon)
            .catch(function () {
              refresh(true);
            });
        return;
      } // a unit reported its state: the server generated the data again
      if (msg.metrics) {
        D.live.metrics = msg.metrics;
        if (!msg.run) {
          rerenderSoon();
          return;
        }
      }
      if (!msg.run) return;
      var runs = D.live.runs || (D.live.runs = []),
        i = runs
          .map(function (r) {
            return r.id;
          })
          .indexOf(msg.run.id);
      var structural =
        i < 0 ||
        runs[i].status !== msg.run.status ||
        (runs[i].current || []).length !== (msg.run.current || []).length;
      if (i < 0) runs.unshift(msg.run);
      else runs[i] = msg.run;
      D.live.at = now();
      if (
        structural &&
        (route.view === "home" || route.view === "workflow") &&
        Date.now() - lastRender > 1500
      )
        rerenderSoon();
      else {
        applyLive();
        updateRunBox();
        sidebar();
      }
      play(V.feedback(route, D, msg.event, msg.run));
    };
  }
  function updateRunBox() {
    var box = document.getElementById("runbox");
    if (!box || route.view !== "workflow" || busy()) return;
    var run = V.pickRun(D, route.wf, route.run);
    var open = box.querySelector("details[open]");
    box.innerHTML = run ? V.runSummary(D, run, now()) : "";
    if (open && box.querySelector("details"))
      box.querySelector("details").open = true;
  }

  // ---------------------------------------------------------------- tokens and pulses
  function play(acts) {
    acts.forEach(function (a) {
      if (a.edge)
        edgeToken(main.querySelectorAll('[data-edge="' + cssq(a.edge) + '"]'));
      if (a.events)
        edgeToken(
          [].filter.call(main.querySelectorAll("[data-events]"), function (g) {
            return g.getAttribute("data-events").indexOf(a.events) >= 0;
          }),
        );
      if (a.prefix)
        edgeToken(
          [].filter.call(main.querySelectorAll("[data-edge]"), function (g) {
            return g.getAttribute("data-edge").indexOf(a.prefix) === 0;
          }),
        );
      if (a.node)
        pulse(
          main.querySelector('.node[data-node="' + cssq(a.node) + '"]'),
          a.cls,
        );
    });
  }
  function cssq(s) {
    return String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }
  function pulse(g, cls) {
    if (!g) return;
    g.classList.remove("pulsing", "good", "bad");
    void g.getBBox();
    g.classList.add("pulsing");
    if (cls) g.classList.add(cls);
    setTimeout(function () {
      g.classList.remove("pulsing", "good", "bad");
    }, 1100);
  }
  function edgeToken(groups) {
    [].forEach.call(groups, function (g) {
      var p = g.querySelector("path.ep"),
        svg = g.ownerSVGElement;
      if (!p || !svg) return;
      if (reduce && reduce.matches) {
        g.classList.add("flash");
        setTimeout(function () {
          g.classList.remove("flash");
        }, 800);
        return;
      }
      var len = p.getTotalLength(),
        dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("r", "6");
      dot.setAttribute("class", "token");
      svg.querySelector(".tokens").appendChild(dot);
      g.classList.add("flash");
      var t0 = performance.now(),
        T = 900;
      (function step(t) {
        var k = Math.min(1, (t - t0) / T),
          e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2,
          pt = p.getPointAtLength(len * e);
        dot.setAttribute("cx", pt.x);
        dot.setAttribute("cy", pt.y);
        if (k < 1 && dot.isConnected) requestAnimationFrame(step);
        else {
          dot.remove();
          g.classList.remove("flash");
        }
      })(t0);
    });
  }

  // ---------------------------------------------------------------- drill-down, count-up
  // The new canvas grows out of the node that was selected (or shrinks back when going up).
  function drill(dir) {
    var c = main.querySelector(".canvas");
    if (!c || !dir || calm()) {
      lastClick = null;
      return;
    }
    c.classList.remove("zoom-in", "zoom-out");
    if (dir === "in" && lastClick) {
      var r = c.getBoundingClientRect();
      c.style.setProperty(
        "--zx",
        Math.round(lastClick.x - (r.left + r.width / 2)) + "px",
      );
      c.style.setProperty(
        "--zy",
        Math.round(
          Math.min(lastClick.y, window.innerHeight) -
            (r.top + Math.min(r.height, window.innerHeight) / 2),
        ) + "px",
      );
    }
    void c.offsetWidth;
    c.classList.add(dir === "in" ? "zoom-in" : "zoom-out");
    c.addEventListener(
      "animationend",
      function () {
        c.classList.remove("zoom-in", "zoom-out");
      },
      { once: true },
    );
    lastClick = null;
  }
  function countUp() {
    var els = main.querySelectorAll("[data-count]"),
      rings = main.querySelectorAll(".rprog[data-ring]");
    if (calm()) return;
    [].forEach.call(rings, function (c) {
      var full = c.getAttribute("stroke-dasharray").split(" ")[1];
      c.style.transition = "none";
      c.setAttribute("stroke-dasharray", "0 " + full);
      void c.getBBox();
      var end = function () {
        c.setAttribute(
          "stroke-dasharray",
          c.getAttribute("data-ring") + " " + full,
        );
      };
      c.style.transition = "";
      requestAnimationFrame(end);
      setTimeout(end, 120); // the timer lands it when frames are throttled
    });
    [].forEach.call(els, function (el) {
      var n = +el.getAttribute("data-count"),
        suf = el.getAttribute("data-suffix") || "",
        t0 = performance.now(),
        T = 700;
      if (!(n > 0)) return;
      (function step(t) {
        var k = Math.min(1, (t - t0) / T),
          e = 1 - Math.pow(1 - k, 3);
        el.textContent = Math.round(n * e) + suf;
        if (k < 1 && el.isConnected) requestAnimationFrame(step);
      })(t0);
      setTimeout(function () {
        el.textContent = n + suf;
      }, T + 80); // final value even when frames are throttled
    });
  }

  // ---------------------------------------------------------------- path highlight on hover or focus
  function highlight(g) {
    var svg = g && g.ownerSVGElement;
    clearHighlight();
    if (!svg) return;
    var id = g.getAttribute("data-node"),
      edges = svg.querySelectorAll(".edge[data-from][data-to]"),
      fwd = {},
      back = {};
    [].forEach.call(edges, function (e) {
      var a = e.getAttribute("data-from"),
        b = e.getAttribute("data-to");
      (fwd[a] = fwd[a] || []).push(b);
      (back[b] = back[b] || []).push(a);
    });
    function reach(start, adj) {
      var seen = {},
        q = [start];
      seen[start] = 1;
      while (q.length) {
        var x = q.shift();
        (adj[x] || []).forEach(function (y) {
          if (!seen[y]) {
            seen[y] = 1;
            q.push(y);
          }
        });
      }
      return seen;
    }
    var down = reach(id, fwd),
      up = reach(id, back);
    if (Object.keys(down).length + Object.keys(up).length <= 2) return;
    svg.classList.add("hl");
    [].forEach.call(svg.querySelectorAll(".node[data-node]"), function (n) {
      var k = n.getAttribute("data-node");
      if (down[k] || up[k]) n.classList.add("on");
    });
    [].forEach.call(edges, function (e) {
      var a = e.getAttribute("data-from"),
        b = e.getAttribute("data-to");
      if ((down[a] && down[b]) || (up[a] && up[b])) e.classList.add("on");
    });
  }
  function clearHighlight() {
    [].forEach.call(main.querySelectorAll("svg.graph.hl"), function (s) {
      s.classList.remove("hl");
    });
    [].forEach.call(main.querySelectorAll("svg.graph .on"), function (x) {
      x.classList.remove("on");
    });
  }
  function nodeOf(t) {
    if (!t || !t.closest) return null;
    var a = t.closest("a.nlink"),
      g = a
        ? a.querySelector(".node[data-node]")
        : t.closest(".node[data-node]");
    return g && g.closest("svg.graph") && !g.closest(".legend") ? g : null;
  }

  // ---------------------------------------------------------------- legend filters (click a state or kind to isolate it)
  function applyFilters() {
    [].forEach.call(
      main.querySelectorAll(".legend button[data-filter]"),
      function (b) {
        b.setAttribute(
          "aria-pressed",
          filters.indexOf(b.getAttribute("data-filter")) >= 0
            ? "true"
            : "false",
        );
      },
    );
    [].forEach.call(main.querySelectorAll(".canvas svg.graph"), function (svg) {
      svg.classList.toggle("filt", filters.length > 0);
      [].forEach.call(svg.querySelectorAll(".node[data-node]"), function (n) {
        n.classList.toggle(
          "fon",
          filters.some(function (f) {
            return n.classList.contains(f);
          }),
        );
      });
    });
  }

  // ---------------------------------------------------------------- jump palette (/ or Ctrl-K)
  var pal = document.getElementById("pal"),
    palQ = document.getElementById("pal-q"),
    palList = document.getElementById("pal-list"),
    palIdx = [],
    palSel = 0,
    palHits = [];
  function openPalette() {
    if (!pal || !pal.showModal) return;
    palIdx = V.searchIndex(D);
    palQ.value = "";
    palFilter();
    if (!pal.open) pal.showModal();
    palQ.focus();
  }
  function palFilter() {
    var q = palQ.value.trim().toLowerCase(),
      toks = q.split(/\s+/).filter(Boolean);
    palHits = palIdx
      .map(function (x) {
        var l = x.label.toLowerCase(),
          all = l + " " + x.sub.toLowerCase();
        if (
          !toks.every(function (t) {
            return all.indexOf(t) >= 0;
          })
        )
          return null;
        return {
          x: x,
          s: !q
            ? 0
            : l === q
              ? 0
              : l.indexOf(q) === 0
                ? 1
                : l.indexOf(q) >= 0
                  ? 2
                  : 3,
        };
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return a.s - b.s;
      })
      .slice(0, 50)
      .map(function (h) {
        return h.x;
      });
    palSel = 0;
    palList.innerHTML = palHits.length
      ? palHits
          .map(function (x, i) {
            return (
              '<li><a id="pal-' +
              i +
              '" role="option" href="' +
              G.esc(x.href) +
              '"' +
              (x.seg ? ' class="seg-' + G.esc(x.seg) + '"' : "") +
              ' aria-selected="' +
              (i === 0) +
              '"><span class="sw" aria-hidden="true"></span><span>' +
              G.esc(x.label) +
              "<br><small>" +
              G.esc(x.sub) +
              "</small></span></a></li>"
            );
          })
          .join("")
      : '<li class="none">Nothing matches. Try a workflow name, a step, a unit id such as U3, or a decision.</li>';
    palQ.setAttribute("aria-activedescendant", palHits.length ? "pal-0" : "");
  }
  function palMove(d) {
    if (!palHits.length) return;
    palSel = (palSel + d + palHits.length) % palHits.length;
    [].forEach.call(palList.querySelectorAll("a"), function (a, i) {
      a.setAttribute("aria-selected", i === palSel ? "true" : "false");
      if (i === palSel) a.scrollIntoView({ block: "nearest" });
    });
    palQ.setAttribute("aria-activedescendant", "pal-" + palSel);
  }
  if (pal) {
    palQ.addEventListener("input", palFilter);
    palQ.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        palMove(1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        palMove(-1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (palHits[palSel]) {
          pal.close();
          location.hash = palHits[palSel].href;
        }
      }
    });
    palList.addEventListener("click", function (e) {
      if (e.target.closest("a")) pal.close();
    });
    pal.addEventListener("click", function (e) {
      if (e.target === pal) pal.close();
    });
    document.getElementById("jump").addEventListener("click", openPalette);
  }

  // ---------------------------------------------------------------- theme
  var themeBtn = document.getElementById("sb-theme");
  function themeLabel() {
    var t = document.documentElement.getAttribute("data-theme");
    themeBtn.textContent = "Theme: " + (t || "system");
  }
  themeBtn.addEventListener("click", function () {
    var t = document.documentElement.getAttribute("data-theme"),
      nx = !t ? "light" : t === "light" ? "dark" : null;
    if (nx) document.documentElement.setAttribute("data-theme", nx);
    else document.documentElement.removeAttribute("data-theme");
    try {
      if (nx) localStorage.setItem("org-theme", nx);
      else localStorage.removeItem("org-theme");
    } catch (e) {
      /* private window */
    }
    themeLabel();
  });
  themeLabel();

  // ---------------------------------------------------------------- wiring
  window.addEventListener("hashchange", function () {
    render(true);
  });
  document.addEventListener("keydown", function (e) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(
      (document.activeElement || {}).tagName || "",
    );
    if (
      (e.key === "/" && !typing) ||
      (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey))
    ) {
      e.preventDefault();
      openPalette();
      return;
    }
    if (e.key !== "Escape" || (pal && pal.open)) return; // the open palette closes itself first
    if (filters.length) {
      filters = [];
      applyFilters();
      return;
    }
    var c = main.querySelector(".panel .close"),
      up = c ? c.getAttribute("href") : V.parent(route, D);
    if (up) location.hash = up;
  });
  main.addEventListener("click", function (e) {
    var g = nodeOf(e.target);
    if (g) {
      var r = g.getBoundingClientRect();
      lastClick = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    var b = e.target.closest && e.target.closest(".legend button[data-filter]");
    if (b) {
      var f = b.getAttribute("data-filter"),
        i = filters.indexOf(f);
      if (i >= 0) filters.splice(i, 1);
      else filters.push(f);
      applyFilters();
    }
    var t = e.target.closest && e.target.closest(".tog[data-toggle]");
    if (t) toggleFold(t);
  });
  main.addEventListener("keydown", function (e) {
    var t = e.target.closest && e.target.closest(".tog[data-toggle]");
    if (t && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      toggleFold(t);
    }
  });
  function toggleFold(t) {
    var k = t.getAttribute("data-toggle"),
      f = (folded[route.wf] = folded[route.wf] || {});
    if (f[k]) delete f[k];
    else f[k] = true;
    render(false);
    var nt = main.querySelector('.tog[data-toggle="' + cssq(k) + '"]');
    if (nt) nt.focus();
  }
  main.addEventListener("pointerover", function (e) {
    var g = nodeOf(e.target);
    if (g) highlight(g);
  });
  main.addEventListener("pointerout", function (e) {
    if (nodeOf(e.target) && !nodeOf(e.relatedTarget)) clearHighlight();
  });
  main.addEventListener("focusin", function (e) {
    var g = nodeOf(e.target);
    if (g) highlight(g);
    else clearHighlight();
  });
  document.getElementById("sb-refresh").addEventListener("click", function () {
    refresh(true);
  });
  document.querySelector("[data-skip]").addEventListener("click", function (e) {
    e.preventDefault();
    main.focus();
  });
  var rt;
  window.addEventListener("resize", function () {
    clearTimeout(rt);
    rt = setTimeout(function () {
      rerenderSoon();
    }, 250);
  });
  setInterval(function () {
    if (pending) rerenderSoon();
    if (anyRunning() && !document.hidden) {
      applyLive();
    }
  }, 1000);

  if (!D) {
    main.innerHTML =
      "<h1>No data</h1><p>data/data.js is missing. Start <code>scripts/serve.py</code> of the status skill, which generates it, and open the page it serves.</p>";
    return;
  }
  render(true);
  if (LIVE) {
    loadAll()
      .then(function () {
        render(false);
      })
      .catch(function (e) {
        refreshErr = String(e.message || e);
        sidebar();
      });
    refresh(true);
    setInterval(function () {
      refresh(false);
    }, 30000);
    connect();
  }
})();
