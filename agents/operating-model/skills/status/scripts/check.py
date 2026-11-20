#!/usr/bin/env python3
"""Check the site without a browser. Standard library only.

  python3 scripts/check.py [--port N] [source options]
                                   static checks, data checks on <data-dir>/data, the node render test when
                                   node is on PATH, and the server checks when serve.py answers on the port

What it checks: every data file parses and data.js holds the same parts; every route the site draws has its
data (segments, items, workflows, units, decisions); index.html loads only local files that exist; no
script, stylesheet or font comes from the network; no en or em dash in the site sources or the generated data;
no all-caps styling; text and graph-mark colors meet WCAG AA (4.5:1 text, 3:1 marks) in light and dark; the node test renders every route and follows every link (when node is found); and
the server refuses traversal, listings, hidden files and foreign Host headers (when it runs); the ingest log
(ingest.py, emit.py) validates reports, detects a tampered or torn chain, lets the newest report win and falls back
to the file when the server is down, all on temporary files; against the running server only refused reports are
sent (bad state, oversize, wrong host, cross site, foreign origin, not JSON), so the real log is never written.
A step that cannot run is reported as SKIPPED, never as passed.
"""
import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
PARTS = ["org", "workflows", "build", "decisions", "language", "live", "meta"]
fails, notes = [], []


def fail(m):
    fails.append(m)


def data_checks(out):
    D = {}
    for p in PARTS:
        f = Path(out) / (p + ".json")
        try:
            D[p] = json.loads(f.read_text())
        except (OSError, ValueError) as e:
            fail("data/%s.json: %s" % (p, e))
    if fails:
        return D
    js = (Path(out) / "data.js").read_text()
    m = re.match(r"window\.ORG_DATA = (.*);\n$", js, re.S)
    if not m:
        fail("data/data.js: not of the form window.ORG_DATA = {...};")
        return D
    full = json.loads(m.group(1))
    for p in PARTS:
        if p not in full:
            fail("data/data.js lacks %s" % p)
    if full.get("meta", {}).get("hash") != D.get("meta", {}).get("hash"):
        fail("data/data.js and data/meta.json are from different generations")
    org, wfs, units = D["org"], D["workflows"], D["build"]["units"]
    uid = {u["id"] for u in units}
    for s in org["segments"]:
        if not s["items"]:
            fail("segment %s has no items" % s["id"])
        if s["id"] not in org["seg_graphs"]:
            fail("segment %s has no graph" % s["id"])
        for i in s["items"]:
            it = org["items"].get(i)
            if not it:
                fail("segment %s names %s, which has no item" % (s["id"], i))
            elif it["kind"] == "workflow" and i not in wfs:
                fail("workflow %s has no workflow data" % i)
    for sid, g in org["seg_graphs"].items():
        ids = {n["id"] for n in g["nodes"]}
        for e in g["edges"]:
            if e["to"] not in ids or (e["from"] not in ids and not e["from"].startswith("start:")):
                fail("segment %s: edge %s>%s has no node" % (sid, e["from"], e["to"]))
    for e in org["edges"]:
        for end in (e["from"], e["to"]):
            if end != "owner" and end not in {s["id"] for s in org["segments"]}:
                fail("organization edge to unknown segment %s" % end)
    for name, w in wfs.items():
        if not w["tree"]:
            fail("workflow %s has no tasks" % name)
    for u in units:
        for d in u["dep"]:
            if d not in uid:
                fail("unit %s needs %s, which is not a unit" % (u["id"], d))
        for i in u["items"]:
            if i not in org["items"]:
                fail("unit %s builds %s, which is not an item" % (u["id"], i))
    for i in org["critical"]["needs_owner"]:
        if i not in {d["id"] for d in D["decisions"]["items"]}:
            fail("open item %s has no decision" % i)
    ids = [d["id"] for d in D["decisions"]["items"]]
    if len(ids) != len(set(ids)):
        fail("decision ids are not unique")
    if not D["language"]["kinds"]:
        fail("process language has no node kinds")
    for r in D["live"]["runs"]:
        if r.get("cost_src") == "journal" and r.get("cost_usd", 0) + 1e-9 < r.get("ledger_usd", 0):
            fail("run %s: journal cost %.4f is below the ledger's step cost %.4f" % (r.get("run_id"), r["cost_usd"], r["ledger_usd"]))
    for w in D["meta"].get("warnings", []):
        notes.append("generator warning: %s" % w)
    print("data: %d segments, %d items, %d workflows, %d units, %d decisions, %d runs" % (
        len(org["segments"]), len(org["items"]), len(wfs), len(units), len(ids), len(D["live"]["runs"])))
    return D


def static_checks(assets):
    assets = Path(assets)
    html = (assets / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="([^"#]+)"', html):
        if re.match(r"[a-z]+:", ref):
            fail("index.html loads %s from outside the site" % ref)
        elif ref.startswith("data/"):
            continue  # generated into <data-dir>/data and served from there
        elif not (assets / ref).is_file():
            fail("index.html loads %s, which does not exist" % ref)
    root = assets.parent
    srcs = [p for p in root.rglob("*") if p.is_file() and p.suffix in (".html", ".css", ".js", ".py", ".md", ".json")
            and "fixture" not in p.parts and p.parent.name != "__pycache__"]
    for p in srcs:
        t = p.read_text()
        rel = p.relative_to(root)
        for ch, name in (("\u2014", "em dash"), ("\u2013", "en dash")):
            if ch in t:
                n = t.count(ch)
                fail("%s: %d %s%s" % (rel, n, name, " (from a source file; fix it there)" if rel.parts[0] == "data" else ""))
        if p.suffix in (".css",) and re.search(r"text-transform:\s*uppercase", t):
            fail("%s: uppercase text transform" % rel)
        if p.suffix in (".html", ".js", ".css") and rel.parts[0] == "assets":
            for m in re.finditer(r"""(?:src=|href=|url\(|fetch\(|import\s)\s*["']?(https?:)?//""", t):
                fail("%s: network reference %r" % (rel, t[m.start():m.start() + 60]))
    for f in ("fonts/atkinson-next-var.ttf", "fonts/atkinson-mono-var.ttf", "fonts/LICENSE.txt", "fonts/OFL.txt"):
        if not (assets / f).is_file():
            fail("missing %s" % f)
    print("static: %d files scanned" % len(srcs))


def _lum(hexc):
    h = hexc.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# text tokens need 4.5:1 (WCAG AA) on surface, surface-2 and ground; graph marks need 3:1 on surface and their own tint
TEXT = ["ink", "ink-2", "ink-3", "accent", "s-done", "s-active", "s-owner", "s-fail", "s-esc", "s-queued",
        "seg-se", "seg-research", "seg-self", "seg-platform"]
MARKS = ["s-done", "s-active", "s-owner", "s-fail", "s-esc", "s-queued", "seg-se", "seg-research", "seg-self", "seg-platform",
         "k-step", "k-check", "k-rubric", "k-gate", "k-event", "k-call", "k-raise", "edge"]
ON_TINT = [("s-done", "s-done-t"), ("s-active", "s-active-t"), ("s-owner", "s-owner-t"), ("s-fail", "s-fail-t"), ("s-esc", "s-esc-t"),
           ("seg-se", "seg-se-t"), ("seg-research", "seg-research-t"), ("seg-self", "seg-self-t"), ("seg-platform", "seg-platform-t")]


def contrast_checks(assets):
    css = (Path(assets) / "css/site.css").read_text()
    blocks = {"light": re.search(r"^:root \{([^}]*)\}", css, re.M), "dark": re.search(r'^:root\[data-theme="dark"\] \{([^}]*)\}', css, re.M)}
    worst = []
    for theme, m in blocks.items():
        if not m:
            fail("css: no %s token block" % theme)
            continue
        tok = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,6})\s*;", m.group(1)))
        if theme == "dark":
            media = re.search(r':root:not\(\[data-theme="light"\]\) \{([^}]*)\}', css)
            if not media or dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,6})", media.group(1))) != tok:
                fail("css: the dark tokens under prefers-color-scheme differ from :root[data-theme=dark]")
        for t in TEXT:
            for bg in ("surface", "surface-2", "ground"):
                if t not in tok or bg not in tok:
                    fail("css %s: missing token --%s or --%s" % (theme, t, bg))
                    continue
                c = contrast(tok[t], tok[bg])
                worst.append(c)
                if c < 4.5:
                    fail("css %s: text --%s on --%s is %.2f:1, needs 4.5:1" % (theme, t, bg, c))
        for t in MARKS:
            c = contrast(tok.get(t, "#000"), tok["surface"])
            if c < 3:
                fail("css %s: graph mark --%s on --surface is %.2f:1, needs 3:1" % (theme, t, c))
        for seg in ("seg-se", "seg-research", "seg-self", "seg-platform"):  # segment-tinted edges: color-mix(hue 72%, surface)
            h, b = tok[seg].lstrip("#"), tok["surface"].lstrip("#")
            mix = "#" + "".join("%02x" % round(int(h[i:i + 2], 16) * 0.72 + int(b[i:i + 2], 16) * 0.28) for i in (0, 2, 4))
            c = contrast(mix, tok["surface"])
            if c < 3:
                fail("css %s: the %s edge (72%% mix) on --surface is %.2f:1, needs 3:1" % (theme, seg, c))
        for t, bg in ON_TINT:
            c = contrast(tok.get(t, "#000"), tok.get(bg, "#fff"))
            if c < 4.5:
                fail("css %s: --%s on its tint --%s is %.2f:1, needs 4.5:1" % (theme, t, bg, c))
    svgcss = css[css.index("svg graph */"):css.index("blocks */")]
    for m in re.finditer(r"font-size:\s*([0-9.]+)px", svgcss):
        if float(m.group(1)) < 12:
            fail("css: a graph label is set at %spx; labels truncate, they never go below 12px" % m.group(1))
    print("contrast: %d text pairs checked in light and dark, lowest %.2f:1" % (len(worst), min(worst) if worst else 0))


def node_test(data_js):
    node = shutil.which("node")
    if not node:
        notes.append("node render test: SKIPPED (node is not on PATH)")
        return
    for t in [str(data_js)]:
        try:
            p = subprocess.run([node, str(SKILL / "tests/render.test.js"), t], capture_output=True, text=True, timeout=240)
        except (OSError, subprocess.SubprocessError) as e:
            notes.append("node render test: SKIPPED (%s)" % e)
            return
        out = (p.stdout + p.stderr).strip().splitlines()
        print("node (%s): %s" % (t, " / ".join(out[-2:])))
        if p.returncode:
            fail("node render test on %s failed:\n    %s" % (t, "\n    ".join(out[-30:])))


def server_checks(port, ingest_log):
    def get(path, host="127.0.0.1:%d" % port, site=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.putrequest("GET", path, skip_host=True)
        c.putheader("Host", host)
        if site:
            c.putheader("Sec-Fetch-Site", site)
        c.endheaders()
        r = c.getresponse()
        body = r.read(2000)
        c.close()
        return r.status, body
    try:
        get("/data/meta.json")
    except OSError:
        notes.append("server checks: SKIPPED (serve.py is not running on 127.0.0.1:%d)" % port)
        return
    want = {"/": 200, "/data/org.json": 200, "/api/live": 200, "/css/": 404, "/data": 404, "/serve.py": 404,
            "/scripts/serve.py": 404, "/../scripts/serve.py": 404, "/%2e%2e/%2e%2e/etc/passwd": 404,
            "/%2e%2e/scripts/serve.py": 404, "/..%2fscripts%2fserve.py": 404, "/.git/config": 404,
            "/data/../ingest/events.jsonl": 404, "/ingest/events.jsonl": 404}
    for path, code in want.items():
        st, _ = get(path)
        if st != code:
            fail("server: GET %s gave %d, wanted %d" % (path, st, code))
    st, _ = get("/", host="evil.example:8765")
    if st != 403:
        fail("server: a foreign Host header gave %d, wanted 403" % st)
    st, _ = get("/data/data.js", site="cross-site")
    if st != 403:
        fail("server: a cross-site request for data.js gave %d, wanted 403" % st)
    print("server: %d paths checked" % (len(want) + 2))
    ingest_server_checks(port, ingest_log)


def ingest_checks():
    import ingest
    import emit
    import serve
    n = 0

    def want(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fail("ingest: " + msg)
    # validation
    for rec, why in [({"unit": "U20", "state": "nope"}, "bad state"), ({"unit": "u20", "state": "building"}, "bad unit id"),
                     ({"unit": "U20", "state": "building", "x": 1}, "unknown field"), ({"unit": "U20", "state": "building", "pr": "176"}, "pr as text"),
                     ({"unit": "U20", "state": "building", "deps": ["U20"]}, "self dependency"), ({"unit": "U20", "state": "building", "title": "a\nb"}, "control character"),
                     ({"unit": "U20", "state": "building", "branch": "a/../b"}, "branch with .."), ({"unit": "U20", "state": "building", "wave": 0}, "wave 0"), ([], "not an object")]:
        want(ingest.validate(rec)[1], "accepts %s" % why)
    ok, err = ingest.validate({"unit": "U13a", "state": "needs-owner", "pr": 176, "deps": ["U1b", "H1"], "branch": "kauki/feat/x", "wave": 3})
    want(ok and not err, "refuses a good report: %s" % err)
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "events.jsonl"
        try:
            ingest.append({"unit": "U1", "state": "nope"}, "test", log)
            want(False, "append wrote a bad report")
        except ValueError:
            want(not log.exists() or not log.read_text(), "a refused report left a line")
        for i, st in enumerate(["building", "review", "failed"]):
            ingest.append({"unit": "U1", "state": st, "title": "t%d" % i, "text": "x%d" % i}, "test", log, now=100 + i)
        ingest.append({"unit": "U2", "state": "building", "pr": 7}, "test", log, now=103)
        r = ingest.read(log)
        want(r["seq"] == 4 and not r["broken"], "chain of 4 lines reads as %s" % r)
        lt = ingest.latest(r["events"])
        want(lt["U1"]["state"] == "failed" and lt["U1"]["title"] == "t2" and lt["U1"]["seq"] == 3, "latest wins: %s" % lt["U1"])
        want(lt["U1"]["about"] == "x0" and lt["U1"]["text"] == "x2", "the first text is not kept as the description: %s" % lt["U1"])
        # projection: newest source wins the state; new units appear; a failure a later report supersedes is gone
        base = [{"id": "U1", "w": 1, "name": "One", "st": "done", "note": "accepted", "dep": [], "what": "x", "tgt": "", "acc": [], "src": "s",
                 "branch": "b1", "pr": 5, "items": [], "findings": []}]
        merged = [{"n": 5, "head": "b1", "merged_at": "2026-11-20T10:00:00Z"}]
        us = {u["id"]: u for u in ingest.project_units(base, {}, merged, {})}
        want(us["U1"]["state"] == "merged" and us["U1"]["state_src"] == "gh", "a merged PR does not make its unit merged: %s" % us["U1"]["state"])
        late = {"U1": {"unit": "U1", "state": "failed", "at": 1795180000.0, "seq": 9}, "U9": {"unit": "U9", "state": "building", "title": "New", "deps": ["U1", "U77"], "at": 1, "seq": 10}}
        us = {u["id"]: u for u in ingest.project_units(base, late, merged, {})}
        want(us["U1"]["st"] == "failed", "a report newer than the merge does not win: %s" % us["U1"]["state"])
        want("U9" in us and us["U9"]["w"] == 2 and us["U9"]["dep"] == ["U1"] and us["U9"]["st"] == "active", "a new unit is not projected right: %s" % us.get("U9"))
        early = {"U1": {"unit": "U1", "state": "failed", "at": 1000.0, "seq": 9}}
        us = {u["id"]: u for u in ingest.project_units(base, early, merged, {})}
        want(us["U1"]["state"] == "merged", "an old failure report beats a later merge: %s" % us["U1"]["state"])
        us = {u["id"]: u for u in ingest.project_units(base, {"U1": {"unit": "U1", "state": "merged", "at": 2e9, "seq": 1}}, [], {5: {"head": "b1", "ci": "passing"}})}
        want("still open" in (us["U1"].get("conflict") or ""), "merged report on an open PR is not flagged")
        # tamper: edit a middle line; append is refused; the file is not rewritten
        lines = log.read_text().splitlines()
        lines[1] = lines[1].replace('"review"', '"merged"')
        log.write_text("\n".join(lines) + "\n")
        before = log.read_bytes()
        r = ingest.read(log)
        want(r["broken"] and r["seq"] == 1 and r["ignored"] == 3, "tampered line 2 not detected: %s" % r)
        try:
            ingest.append({"unit": "U1", "state": "done"}, "test", log)
            want(False, "append onto a broken chain")
        except ingest.ChainBroken:
            want(log.read_bytes() == before, "the broken log was rewritten")
        # reorder and torn tail
        log2 = Path(d) / "b.jsonl"
        for st in ("building", "review"):
            ingest.append({"unit": "U3", "state": st}, "test", log2)
        a, b = log2.read_text().splitlines()
        log2.write_text(b + "\n" + a + "\n")
        want(ingest.read(log2)["broken"], "reordered lines not detected")
        log2.write_text(a + "\n" + b[:20])
        want(ingest.read(log2)["broken"] and ingest.read(log2)["seq"] == 1, "torn tail not detected")
        # emit.py: server down falls back to the file; a refused report is never written
        log3 = Path(d) / "c.jsonl"
        rc, msg = emit.emit({"unit": "U5", "state": "ci", "pr": 3}, "http://127.0.0.1:9/api/ingest", log3)
        e3 = ingest.read(log3)["events"]
        want(rc == 0 and len(e3) == 1 and e3[0]["src"] == "file" and e3[0]["state"] == "ci", "fallback append: %s %s" % (rc, msg))
        rc, msg = emit.emit({"unit": "U5", "state": "nope"}, "http://127.0.0.1:9/api/ingest", log3)
        want(rc == 1 and len(ingest.read(log3)["events"]) == 1, "fallback wrote a bad report: %s" % msg)
    # org.metric reader (live.py): last value per metric across ledgers; a ledger without a header is no run
    import live
    with tempfile.TemporaryDirectory() as d:
        def ledger(path, bodies):
            rows, prev = [], None
            for i, (kind, body) in enumerate(bodies, 1):
                rows.append(json.dumps({"seq": i, "prev": prev, "kind": kind, "body": body, "mac": "m%d" % i}))
                prev = "m%d" % i
            Path(path).write_text("\n".join(rows) + "\n")
        l1, l2 = Path(d) / "a.ledger", Path(d) / "b.ledger"
        ledger(l1, [("header", {"run_id": "r1", "workflow": "tdd-unit", "input": {}}),
                    ("log", {"type": "org.metric", "metric": "lead-time", "value": 5, "t": 1}),
                    ("log", {"type": "org.metric", "metric": "lead-time", "value": 3, "reason": "newer", "t": 2}),
                    ("feed", {"event": {"type": "org.metric", "metric": "escapes", "value": 0}})])
        ledger(l2, [("org.metric", {"metric": "cost-per-unit", "value": 1.5})])
        lv = live.Live({"state_dirs": [], "ledgers": [str(l1), str(l2)]})
        lv.poll()
        snap = lv.snapshot()
        m = snap["metrics"]
        want(m.get("lead-time", {}).get("value") == 3 and m["lead-time"].get("reason") == "newer", "org.metric: not the last value: %s" % m.get("lead-time"))
        want(m.get("escapes", {}).get("value") == 0, "org.metric in body.event not read: %s" % m)
        want(m.get("cost-per-unit", {}).get("value") == 1.5, "org.metric from a ledger without a header not read: %s" % m)
        want(len(snap["runs"]) == 1 and snap["runs"][0]["workflow"] == "tdd-unit", "a metric-only ledger shows as a run: %s" % [r["workflow"] for r in snap["runs"]])
    # rate cap
    bk = serve.Bucket(3, 60)
    want([bk.take() for _ in range(4)] == [True, True, True, False], "rate cap of 3 lets a 4th through")
    print("ingest: %d checks on temporary logs" % n)


def ingest_server_checks(port, ingest_log):
    def post(body, host="127.0.0.1:%d" % port, ctype="application/json", extra=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.putrequest("POST", "/api/ingest", skip_host=True)
        c.putheader("Host", host)
        c.putheader("Content-Type", ctype)
        c.putheader("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            c.putheader(k, v)
        c.endheaders()
        c.send(body)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status
    try:
        size = Path(ingest_log).stat().st_size
    except OSError:
        size = None
    good = json.dumps({"unit": "U1", "state": "building"}).encode()
    cases = [("bad state", post(json.dumps({"unit": "U1", "state": "nope"}).encode()), 400),
             ("unknown field", post(json.dumps({"unit": "U1", "state": "building", "x": 1}).encode()), 400),
             ("not JSON", post(b"{nope"), 400),
             ("oversize", post(json.dumps({"unit": "U1", "state": "building", "text": "a" * 5000}).encode()), 413),
             ("wrong host", post(good, host="evil.example:8765"), 403),
             ("cross site", post(good, extra={"Sec-Fetch-Site": "cross-site"}), 403),
             ("foreign origin", post(good, extra={"Origin": "http://evil.example"}), 403),
             ("text/plain form", post(good, ctype="text/plain"), 415)]
    for name, got, code in cases:
        if got != code:
            fail("server ingest: %s gave %d, wanted %d" % (name, got, code))
    try:
        after = Path(ingest_log).stat().st_size
    except OSError:
        after = None
    if after != size:
        fail("server ingest: a refused report changed the ingest log")
    print("server ingest: %d refused reports checked, the log unchanged" % len(cases))


def main(argv=None):
    import config

    ap = argparse.ArgumentParser(description="Check the site without a browser.")
    config.add_args(ap)
    ap.add_argument("--port", type=int, default=8765, help="where serve.py runs, for the server checks")
    a = ap.parse_args(argv)
    try:
        cfg = config.resolve(a)
    except config.ConfigError as e:
        ap.error(str(e))
    data_checks(cfg.out_dir)
    ingest_checks()
    static_checks(config.ASSETS)
    contrast_checks(config.ASSETS)
    if not fails:
        node_test(cfg.out_dir / "data.js")
    server_checks(a.port, cfg.ingest_log)
    for n in notes:
        print("note:", n)
    if fails:
        print("FAIL")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
