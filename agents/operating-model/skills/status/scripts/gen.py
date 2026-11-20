#!/usr/bin/env python3
"""Generate <data-dir>/data/*.json and data.js for the site. Needs PyYAML (the workflows are YAML).

Run:  python3 scripts/gen.py [source options, see config.py]
      python3 scripts/gen.py --simulate-active U19,U3 --fail-pr 175 --needs-seg platform --out DIR
Reads: the org root, the layout, the optional work package (status-units.json, run-log.md, owner-decisions.md,
agent-plans/, findings/, site.json), the optional language page, two `gh pr list` calls (open, merged; skipped
with --no-gh), the ingest log (see ingest.py) and the run ledgers and state folders given. Writes only into the
output directory, each file by an atomic replace.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402
import orgdata as S  # noqa: E402
import live  # noqa: E402
import ingest  # noqa: E402

LANG_KEEP = ["An organization is a set of workflows", "One workflow, written in it",
             "What the organization may do to a workflow", "How workflows relate", "Reusing an existing format",
             "Settled", "A full example: software development in OWS"]
WARN = []


def warn(msg):
    WARN.append(msg)
    print("warning:", msg, file=sys.stderr)


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# ---------------------------------------------------------------- workflow nodes
def node_json(n, org, floors, wf):
    t, o, k = n["t"], n["org"], n["kind"]
    roles = org["manifest"]["roles"]
    d = {"key": n["key"], "name": n["name"], "kind": k, "label": S.KIND.get(k, k)}
    for f in ("by", "role", "signer", "network"):
        if o.get(f):
            d[f] = o[f]
    if o.get("role"):
        d["chain"] = S.chain(o["role"], roles)[1:]
        d["role_known"] = o["role"] in roles or o["role"] == "owner"
    if k not in ("for", "fork", "try", "do"):
        d["floor"] = S.is_floor(n, floors)
    if t.get("if"):
        d["if"], d["if_read"] = str(t["if"]), S.short(t["if"])
    if isinstance(t.get("then"), str):
        d["then"] = t["then"]
    if t.get("timeout"):
        d["timeout"] = S.human_dur(t["timeout"].get("after"))
    if "run" in t and "shell" in t["run"]:
        sh = t["run"]["shell"]
        d["command"] = " ".join([sh["command"]] + [str(a) for a in sh.get("arguments", [])])
        d["evidence"] = sh["command"] == "tdd-evidence"
        if t["run"].get("await") is False:
            d["no_await"] = True
    if k == "call":
        w = t["run"]["workflow"]
        d["call"] = {"name": w["name"], "version": str(w.get("version", "")), "input": json.dumps(w.get("input")),
                     "known": w["name"] in org["wf"]}
    if k == "emit":
        ty = S.event_of(t, "emit")
        d["emits"] = {"type": ty, "starts": [x for x, v in org["wf"].items() if S.start_type(v["doc"]) == ty]}
    if k in ("gate", "listen"):
        d["listens"] = {"type": S.event_of(t, "listen")}
        if "until" in t["listen"]["to"]:
            d["listens"]["until"] = str(t["listen"]["to"].get("until"))
    if k == "raise":
        er = t["raise"]["error"]
        d["raise"] = {"title": er.get("title", ""), "status": er.get("status"), "to": o.get("to")}
    if k == "switch":
        d["cases"] = []
        for c in t["switch"]:
            (cn, cv), = c.items()
            d["cases"].append({"name": cn, "when": str(cv["when"]) if cv.get("when") else None,
                               "when_read": S.short(cv["when"]) if cv.get("when") else None, "then": cv.get("then", "continue")})
    if k == "for":
        f = t["for"]
        src = f.get("in")
        d["loop"] = {"each": f.get("each"), "in": json.dumps(src) if isinstance(src, list) else str(src),
                     "bound": ("%d %s" % (len(src), "rounds" if "while" in t else "items")) if isinstance(src, list)
                     else "the collection, at most %d items" % S.COLLECTION_CAP,
                     "rework": "while" in t}
        if t.get("while"):
            d["loop"]["while"], d["loop"]["while_read"] = str(t["while"]), S.short(t["while"])
    if k == "fork":
        d["fork"] = {"compete": bool(t["fork"].get("compete"))}
    acc = []
    checks = org["manifest"].get("checks", {})
    for a in o.get("acceptance", []) or []:
        if "check" in a:
            acc.append({"type": "check", "id": a["check"], "cls": checks.get(a["check"]),
                        "reads": S.md_inline(org["check_reads"][a["check"]]) if a["check"] in org["check_reads"] else None})
        elif "rubric" in a:
            title, rules = S.rubric(org["root"], a["rubric"])
            acc.append({"type": "rubric", "path": a["rubric"], "judge": a.get("judge"), "sample": a.get("sample"),
                        "title": title, "rules": [S.md_inline(r) for r in rules]})
        elif "human" in a:
            acc.append({"type": "human", "text": a["human"]})
    if acc:
        d["acceptance"] = acc
    ms = []
    for m in o.get("metrics", []) or []:
        x = org["metrics"].get(m)
        tg = org["manifest"].get("targets", {}).get(m)
        ms.append({"id": m, "formula": x.get("formula") if x else None, "unit": x.get("unit") if x else None,
                   "better": x.get("better") if x else None, "target": S.target_text(tg) if tg else None})
    if ms:
        d["metrics"] = ms
    if o.get("brief"):
        p = org["root"] / o["brief"]
        d["brief"] = {"path": o["brief"], "html": S.md(p.read_text()) if p.exists() else None}
        if not p.exists():
            warn("brief missing: %s" % o["brief"])
    if "children" in n:
        d["children"] = [node_json(c, org, floors, wf) for c in n["children"]]
    if "branches" in n:
        d["branches"] = [[node_json(c, org, floors, wf) for c in b] for b in n["branches"]]
    return d


def workflow_json(name, w, org, called_by, starts, no_listener):
    man = org["manifest"]
    doc = w["doc"]["document"]
    floors = man["workflows"].get(name, {}).get("floors", [])
    tree = [node_json(n, org, floors, name) for n in w["tree"]]
    used = {}
    for n in S.walk(w["tree"]):
        for m in n["org"].get("metrics", []) or []:
            used.setdefault(m, []).append(n["name"])
    metrics = []
    for m, nodes in used.items():
        x = org["metrics"].get(m, {})
        tg = man.get("targets", {}).get(m)
        metrics.append({"id": m, "unit": x.get("unit"), "scope": x.get("scope"), "better": x.get("better"),
                        "formula": x.get("formula"), "target": S.target_text(tg) if tg else None, "used_by": nodes})
    used_roles = []
    for n in S.walk(w["tree"]):
        for r in [n["org"].get("role"), n["org"].get("to"), n["org"].get("signer")] + [a.get("judge") for a in n["org"].get("acceptance", []) or []]:
            if r and r not in used_roles:
                used_roles.append(r)
    roles = []
    for r in used_roles:
        if r == "owner":
            roles.append({"id": r, "about": "the head of the organization (%s)" % man.get("owner", "")})
        elif r in man["roles"]:
            roles.append({"id": r, "chain": S.chain(r, man["roles"])[1:], "may_spawn": man["roles"][r].get("may-spawn", []),
                          "rungs": man["roles"][r].get("rungs", [])})
        else:
            roles.append({"id": r, "about": "not in the manifest"})
    mf = man["workflows"].get(name, {}).get("floors")
    yaml_floors = [n["name"] for n in S.walk(w["tree"]) if n["org"].get("floor")]
    return {"id": name, "path": w["path"], "title": doc.get("title", ""), "summary": doc.get("summary", ""),
            "version": str(doc.get("version", "")), "describe": org["describe"].get(name), "start": starts.get(name),
            "called_by": called_by.get(name, []), "registered": name in man["workflows"],
            "policy": ((doc.get("metadata") or {}).get("org") or {}).get("policy") or [],
            "floors": mf if mf is not None else yaml_floors, "floors_src": "manifest" if mf is not None else "YAML",
            "no_listener": [t for a, t in no_listener if a == name], "tree": tree, "metrics": metrics, "roles": roles,
            "vetoes": man.get("vetoes", []) if name in man["workflows"] else []}


# ---------------------------------------------------------------- process language
def language(org):
    counts = {}
    for name, w in org["wf"].items():
        for n in S.walk(w["tree"]):
            k = n["kind"]
            c = counts.setdefault(k, {"kind": k, "label": S.KIND.get(k, k), "count": 0, "by_wf": {}})
            c["count"] += 1
            c["by_wf"][name] = c["by_wf"].get(name, 0) + 1
    group = {"step": "work", "call": "work", "set": "work", "gate": "wait", "listen": "wait", "wait": "wait",
             "emit": "signal", "raise": "signal", "switch": "flow", "for": "flow", "fork": "flow", "try": "flow", "do": "flow"}
    kinds = []
    for k, label in S.KIND.items():
        if k in ("trigger", "task"):
            continue
        c = counts.get(k, {"kind": k, "label": label, "count": 0, "by_wf": {}})
        c["group"] = group.get(k, "other")
        kinds.append(c)
    # connections, counted from the tree
    conn = {"sequence": 0, "then": 0, "case": 0, "call": 0, "event": 0, "loop": 0}
    for name, w in org["wf"].items():
        st = S.start_type(w["doc"])
        for n in S.walk(w["tree"]):
            t = n["t"]
            conn["sequence"] += 1
            if isinstance(t.get("then"), str):
                conn["then"] += 1
            if n["kind"] == "switch":
                conn["case"] += len(t["switch"])
            if n["kind"] == "call":
                conn["call"] += 1
            if n["kind"] == "for":
                conn["loop"] += 1
            if n["kind"] == "emit":
                ty = S.event_of(t, "emit")
                conn["event"] += sum(1 for v in org["wf"].values() if S.start_type(v["doc"]) == ty)
        del st
    connections = [
        {"id": "sequence", "label": "sequence", "about": "the next task in YAML order", "count": conn["sequence"]},
        {"id": "then", "label": "then", "about": "a jump to a named task", "count": conn["then"]},
        {"id": "case", "label": "switch case", "about": "a guarded jump, one per case", "count": conn["case"]},
        {"id": "loop", "label": "loop", "about": "for over items, or a rework loop with while", "count": conn["loop"]},
        {"id": "call", "label": "call", "about": "run another workflow and wait for it", "count": conn["call"]},
        {"id": "event", "label": "event", "about": "an emit that starts another workflow", "count": conn["event"]},
    ]
    checks = []
    used = {}
    for name, w in org["wf"].items():
        for n in S.walk(w["tree"]):
            for a in n["org"].get("acceptance", []) or []:
                if "check" in a:
                    used.setdefault(a["check"], []).append("%s/%s" % (name, n["key"]))
    for cid, cls in org["manifest"].get("checks", {}).items():
        checks.append({"id": cid, "cls": cls, "reads": S.md_inline(org["check_reads"][cid]) if cid in org["check_reads"] else None,
                       "used_by": used.get(cid, [])})
    return {"kinds": kinds, "connections": connections, "checks": checks, "sections": lang_sections(org["language_page"])}


def lang_sections(page):
    if not page:
        return []
    t = page.read_text()
    if "<main>" not in t or "</main>" not in t:
        warn("%s has no <main>; the language view shows only the generated part" % page.name)
        return []
    main = t[t.index("<main>") + 6:t.index("</main>")]
    main = re.sub(r'<nav class="pages".*?</nav>', "", main, flags=re.S)
    parts = re.split(r"<h2>(.*?)</h2>", main)
    out = []
    for i in range(1, len(parts), 2):
        title, body = parts[i], parts[i + 1]
        if title not in LANG_KEEP:
            continue
        body = re.sub(r'<pre class="mermaid">(.*?)</pre>', lambda m: '<pre class="y">%s</pre>' % m.group(1).strip("\n"), body, flags=re.S)
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        # all-caps band labels in the old figures become sentence case
        body = re.sub(r'(<text class="bl"[^>]*>)([^<]+)(</text>)', lambda m: m.group(1) + m.group(2)[:1] + m.group(2)[1:].lower() + m.group(3), body)
        body = body.replace('id="p1"', 'id="lm-%d"' % i).replace("url(#p1)", "url(#lm-%d)" % i)
        for mid in set(re.findall(r'<marker id="([^"]+)"', body)):
            if not mid.startswith("lm-"):
                body = body.replace('id="%s"' % mid, 'id="lm-%d-%s"' % (i, mid)).replace("url(#%s)" % mid, "url(#lm-%d-%s)" % (i, mid))
        out.append({"id": slug(title), "title": title, "html": body.strip()})
    return out


# ---------------------------------------------------------------- assemble
def gh_list(repo, state, fields):
    """One gh pr list call. No repo (--no-gh): (None, "off")."""
    if not repo:
        return None, "off"
    cmd = ["gh", "pr", "list", "--repo", repo, "--state", state, "--limit", "200", "--json", fields]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        if p.returncode:
            raise RuntimeError(p.stderr.strip()[:200] or "exit %d" % p.returncode)
        return json.loads(p.stdout), None
    except Exception as e:  # noqa: BLE001  any failure falls back to the unit notes
        return None, str(e)


def build(cfg, simulate=(), fail_prs=(), needs_seg=()):
    wp = cfg.work_package
    lay = S.load_layout(cfg.layout)
    site = S.load_site(wp)
    components = [(c["id"], c["name"], site["component_units"].get(c["id"], []), c.get("files", [])) for c in lay["components"]]
    rows = S.log_rows(wp)
    units = S.load_units(wp, rows)
    by = {u["id"]: u for u in units}
    inflight = S.followups(wp, rows)
    for uid in inflight:
        if uid in by and by[uid]["st"] == "done":
            by[uid]["st"], by[uid]["note"] = "active", "%s in flight" % inflight[uid]["label"]
    br = S.branches(wp)
    prs_raw, gh_err = gh_list(cfg.repo, "open", "number,title,isDraft,headRefName,statusCheckRollup,updatedAt")
    merged_raw, merged_err = gh_list(cfg.repo, "merged", "number,headRefName,mergedAt")
    if merged_raw is None and cfg.repo:
        warn("gh merged pull requests: %s" % merged_err)
    merged = [{"n": p["number"], "head": p["headRefName"], "merged_at": p["mergedAt"]} for p in merged_raw or []]
    prs = {}
    if prs_raw is not None:
        for p in prs_raw:
            prs[p["number"]] = {"n": p["number"], "title": p["title"], "draft": p["isDraft"], "ci": S.ci_state(p["statusCheckRollup"]),
                                "head": p["headRefName"], "updated": p.get("updatedAt")}
    for n in fail_prs:
        prs.setdefault(n, {"n": n, "title": "simulated pull request", "draft": False, "head": "sim"})["ci"] = "failing"
        gh_err = None if prs_raw is not None or fail_prs else gh_err
    head2pr = {v["head"]: k for k, v in prs.items()}
    findings = S.findings(wp)
    org = S.load_org(cfg.org_root)
    org.update(root=cfg.org_root, describe=lay["describe"], language_page=cfg.language_page)
    calls, emits, called_by = [], [], {}
    for name, w in org["wf"].items():
        for n in S.walk(w["tree"]):
            if n["kind"] == "call":
                tgt = n["t"]["run"]["workflow"]["name"]
                if (name, tgt) not in calls:
                    calls.append((name, tgt))
                called_by.setdefault(tgt, [])
                if name not in called_by[tgt]:
                    called_by[tgt].append(name)
            if n["kind"] == "emit":
                emits.append((name, S.event_of(n["t"], "emit")))
    starts = {name: S.start_type(w["doc"]) for name, w in org["wf"].items()}
    segments = [dict(s, items=list(s["items"])) for s in lay["segments"]]
    seg_of = {i: s["id"] for s in segments for i in s["items"]}
    loose = [name for name in org["wf"] if name not in seg_of]
    if loose:  # a workflow the layout does not place still gets a segment, so every route has its data
        segments.append({"id": "other", "name": "Other workflows", "items": loose,
                         "about": "Workflows in the org root that no segment of the layout names."})
        seg_of.update({name: "other" for name in loose})
    item_of_unit = {}
    for wf, us in site["unit_map"].items():
        for u in us:
            item_of_unit.setdefault(u, []).append(wf)
    for cid, _, cu, _ in components:
        for u in cu:
            item_of_unit.setdefault(u, []).append(cid)
    for u in units:
        u["branch"] = br.get(u["id"])
        note_pr = re.search(r"PR #?(\d+)", u.get("note", ""))
        fallback = u.get("log_pr") or (int(note_pr.group(1)) if note_pr else None)
        u["pr"] = head2pr.get(u["branch"]) if u["branch"] in head2pr else fallback
        u["pr_open"] = u["pr"] in prs
        u["findings"] = [f for f in findings if re.match(r"%s-" % re.escape(u["id"]), f)]
        u["followup"] = inflight.get(u["id"])
        u["items"] = item_of_unit.get(u["id"], [])
        u.pop("log_pr", None)
    ing = ingest.read(cfg.ingest_log)
    if ing["broken"]:
        warn("ingest log: %s; %d lines ignored" % (ing["broken"], ing["ignored"]))
    units = ingest.project_units(units, ingest.latest(ing["events"]), merged, prs, warn)
    by = {u["id"]: u for u in units}
    for uid in simulate:  # after the projection, so a simulated state is what the fixture shows
        by[uid].update(st="active", state="building", note="simulated for a check")

    decisions = copy.deepcopy(site["decisions"])
    open_dec = []
    for d in decisions:
        d.setdefault("seg", [])
        d["found"] = bool(d.get("quote")) and d["quote"] in S._read(wp, d.get("src", ""))
        if not d["found"]:
            warn("decision source text not found: %r in %s" % (d["quote"], d["src"]))
        best = -1
        for pat, state, text in d.pop("updates", []):
            for i, r in enumerate(rows):
                if re.search(pat, r) and i >= best:
                    best, d["state"], d["text"], d["src"] = i, state, text, "run-log.md"
        for sid in needs_seg:
            if sid not in d["seg"] and d["state"] in S.OPEN_STATES and d is decisions[0]:
                d["seg"] = d["seg"] + [sid]
        d["open"] = d["state"] in S.OPEN_STATES
        d["id"] = slug(d["title"])
        if d["open"]:
            open_dec.append(d)

    items = {}
    for name in org["wf"]:
        us = [u["id"] for u in units if name in u["items"]]
        items[name] = {"id": name, "name": name, "kind": "workflow", "seg": seg_of.get(name), "units": us}
    for cid, cname, cu, files in components:
        fl = []
        for f in files:
            p = cfg.org_root / f
            fl.append({"path": f, "size": ("%d files" % len(list(p.iterdir()))) if p.is_dir() else
                       ("%d lines" % len(p.read_text().splitlines())) if p.exists() else None})
        items[cid] = {"id": cid, "name": cname, "kind": "component", "seg": "platform", "units": [u for u in cu if u in by], "files": fl}
    for u in units:
        u["items"] = [i for i in u["items"] if i in items]
    for it in items.values():
        st = [by[u]["st"] for u in it["units"]]
        it["st"] = next((x for x in ("active", "failed", "gate") if x in st), "done")
        it["prs"] = sorted({by[u]["pr"] for u in it["units"] if by[u].get("pr") in prs})
        if it["kind"] == "workflow":
            doc = org["wf"][it["id"]]["doc"]["document"]
            it.update(title=doc.get("title", ""), summary=doc.get("summary", ""), start=starts.get(it["id"]),
                      called_by=called_by.get(it["id"], []), registered=it["id"] in org["manifest"]["workflows"])
        else:
            it["summary"] = " ".join(by[u]["what"] for u in it["units"][:1])
    segs = []
    for s in segments:
        its = [i for i in s["items"] if i in items]
        ist = [items[i]["st"] for i in its]
        st = ("active" if "active" in ist else "failed" if "failed" in ist else
              "gate" if "gate" in ist or any(s["id"] in d["seg"] for d in open_dec) else "done")
        segs.append({"id": s["id"], "name": s["name"], "about": s["about"], "st": st, "items": its,
                     "prs": sorted({p for i in its for p in items[i]["prs"]}),
                     "needs": [d["id"] for d in open_dec if s["id"] in d["seg"]]})

    # organization edges, same rules as status.py
    edges = []
    ext = {}
    for name, typ in starts.items():
        if typ:
            ext.setdefault(seg_of.get(name), []).append(typ)
    gates = {}
    for name, w in org["wf"].items():
        for n in S.walk(w["tree"]):
            if n["kind"] == "gate":
                gates.setdefault(seg_of.get(name), set()).add(S.event_of(n["t"], "listen"))
    for sid, typs in ext.items():
        edges.append({"from": "owner", "to": sid, "label": ["starts: " + t for t in sorted(set(typs))] +
                      ["decides: " + g for g in sorted(gates.get(sid, []))], "kind": "start", "events": sorted(set(typs))})
    cross = {}
    for a, b in calls:
        if seg_of.get(a) != seg_of.get(b):
            cross.setdefault((seg_of[a], seg_of[b]), []).append("calls " + b)
    for a, typ in emits:
        for b, st in starts.items():
            if st == typ and seg_of.get(a) != seg_of.get(b):
                cross.setdefault((seg_of[a], seg_of[b]), []).append(typ)
    for (a, b), labs in cross.items():
        edges.append({"from": a, "to": b, "label": labs, "kind": "flow"})
    for x in lay["inferred_edges"]:
        a, b, lab, why = x["from"], x["to"], x["label"], x.get("why")
        if a not in seg_of.values() or b not in seg_of.values():
            continue
        edges.append({"from": a, "to": b, "label": [lab], "why": why, "kind": "inferred", "inferred": True})
    no_listener = sorted({(a, t) for a, t in emits if not any(st == t for st in starts.values())})

    seg_graphs = {}
    for s in segs:
        nodes = [{"id": i} for i in s["items"]]
        ids = list(s["items"])
        e2 = []
        if s["id"] == "platform":
            comp_of = {u: c[0] for c in components for u in c[2]}
            raw = set()
            for c in components:
                for u in c[2]:
                    for d in by.get(u, {"dep": []})["dep"]:
                        if d in comp_of and comp_of[d] != c[0]:
                            raw.add((comp_of[d], c[0]))
            red = {(a, b) for a, b in raw if not any((a, m) in raw and (m, b) in raw for m in ids)}
            e2 = [{"from": a, "to": b, "label": ["needed by"], "kind": "dep"} for a, b in sorted(red)]
        else:
            for a, b in calls:
                if a in ids and b in items:
                    if b not in [n["id"] for n in nodes]:
                        nodes.append({"id": b, "ext": True, "seg": seg_of.get(b)})
                    e2.append({"from": a, "to": b, "label": ["calls"], "kind": "call"})
            for a, typ in emits:
                for b, st in starts.items():
                    if st == typ and a in ids and b in ids:
                        e2.append({"from": a, "to": b, "label": [typ], "kind": "event", "event": typ})
            for i in ids:
                if starts.get(i):
                    e2.append({"from": "start:" + starts[i], "to": i, "label": [starts[i]], "kind": "start", "event": starts[i]})
        seg_graphs[s["id"]] = {"nodes": nodes, "edges": e2}

    def ulist(st):
        return [{"unit": u["id"], "name": u["name"], "note": u["note"], "state": u["state"], "items": u["items"]} for u in units if u["st"] == st]
    building = ulist("active")
    failing = [p for p in prs.values() if p["ci"] == "failing"]
    cis = {}
    for p in prs.values():
        cis[p["ci"]] = cis.get(p["ci"], 0) + 1
    gh_ok = prs_raw is not None or bool(fail_prs)
    critical = {"building": building, "needs_owner": [d["id"] for d in open_dec], "failing": failing,
                "owner_units": ulist("gate"), "failing_units": ulist("failed"),
                "gh_error": None if gh_ok or not cfg.repo else gh_err, "ci": cis, "open_prs": len(prs),
                "ready_prs": sorted(n for n, p in prs.items() if not p["draft"])}

    workflows = {name: workflow_json(name, w, org, called_by, starts, no_listener) for name, w in org["wf"].items()}
    lang = language(org)
    log = []
    for r in rows:
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", r)
        if m:
            log.append({"date": m.group(1), "html": S.md_inline(m.group(2))})
    owner = S._read(wp, "owner-decisions.md")
    data = {
        "org": {"segments": segs, "items": items, "edges": edges, "seg_graphs": seg_graphs,
                "no_listener": [{"wf": a, "event": t} for a, t in no_listener], "critical": critical,
                "totals": {"done": sum(1 for u in units if u["st"] == "done"), "units": len(units)}},
        "workflows": workflows,
        "build": {"units": units, "waves": max((u["w"] for u in units), default=0), "prs": {str(k): v for k, v in prs.items()},
                  "ingest": {"seq": ing["seq"], "events": len(ing["events"]), "broken": ing["broken"], "ignored": ing["ignored"],
                             "path": tilde(cfg.ingest_log)},
                  "merged_prs": len(merged)},
        "decisions": {"items": decisions, "owner_html": S.md(owner) if owner else "", "log": log[::-1][:80], "log_rows": len(log)},
        "language": lang,
    }
    return data, gh_ok, gh_err, ing["seq"]


def atomic_write(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def tilde(p):
    """A path for display: the home folder as ~, so generated data does not spell out the user's home."""
    s, home = str(p), str(Path.home())
    return "~" + s[len(home):] if home != "/" and (s == home or s.startswith(home + "/")) else s


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the organization site data.")
    config.add_args(ap)
    ap.add_argument("--simulate-active", default="", help="unit ids shown as building (needs --out)")
    ap.add_argument("--fail-pr", default="", help="pull request numbers shown as failing (needs --out)")
    ap.add_argument("--needs-seg", default="", help="segments the first open decision locks (needs --out)")
    ap.add_argument("--out", help="output folder (default: <data-dir>/data)")
    a = ap.parse_args(argv)
    try:
        cfg = config.resolve(a)
    except config.ConfigError as e:
        ap.error(str(e))
    sim = [x for x in a.simulate_active.split(",") if x]
    fails = [int(x) for x in a.fail_pr.split(",") if x]
    needs = [x for x in a.needs_seg.split(",") if x]
    out = Path(a.out).resolve() if a.out else cfg.out_dir
    if (sim or fails or needs or cfg.ingest) and out == cfg.out_dir:
        ap.error("simulated states and another ingest log need --out DIR (the served data never holds them)")
    out.mkdir(parents=True, exist_ok=True)
    del S.WARN[:]
    del WARN[:]
    data, gh_ok, gh_err, ing_seq = build(cfg, sim, fails, needs)
    lv = live.Live({"state_dirs": cfg.state_dirs, "ledgers": cfg.ledgers, "org_root": str(cfg.org_root)})
    lv.poll()
    snap = lv.snapshot()
    body = json.dumps(data, sort_keys=True, default=str)
    now = datetime.datetime.now()
    wp = cfg.work_package
    meta = {"generated": now.timestamp(), "generated_text": now.strftime("%Y-%m-%d %H:%M"),
            "hash": hashlib.sha256(body.encode()).hexdigest()[:16],
            "gh": "off" if not cfg.repo else "live" if gh_ok else "failed: %s" % gh_err,
            "simulated": bool(sim or fails or needs or cfg.ingest), "ingest_seq": ing_seq,
            "sources": {"org_root": tilde(cfg.org_root), "work_package": tilde(wp) if wp else None,
                        "prs": "gh pr list --repo %s (open and merged)" % cfg.repo if cfg.repo else None,
                        "language": tilde(cfg.language_page) if cfg.language_page else None,
                        "ingest": tilde(cfg.ingest_log), "ledgers": [tilde(x) for x in cfg.ledgers],
                        "state_dirs": [tilde(x) for x in cfg.state_dirs]},
            "warnings": S.WARN + WARN}
    for name, part in list(data.items()) + [("live", snap), ("meta", meta)]:
        atomic_write(out / ("%s.json" % name), json.dumps(part, indent=1, default=str))
    full = dict(data, live=snap, meta=meta)
    atomic_write(out / "data.js", "window.ORG_DATA = %s;\n" % json.dumps(full, default=str).replace("</", "<\\/"))
    print("ok %s (hash %s, gh %s, %d warnings)" % (out, meta["hash"], meta["gh"], len(meta["warnings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
