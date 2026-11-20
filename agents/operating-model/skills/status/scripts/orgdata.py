"""Readers for the org root, the layout and the optional work package. gen.py builds the site data from them.

The org root needs PyYAML (the workflows are YAML). Everything else is standard library. Every work package
reader returns an empty result when the work package or one of its files is absent.
"""

import html
import json
import re
from pathlib import Path

COLLECTION_CAP = 1000  # expression collections are capped at 1000 items
OPEN_STATES = ("waits for you", "for review")
KIND = {"step": "step", "call": "call", "gate": "gate", "listen": "listen", "wait": "wait", "emit": "emit",
        "raise": "escalation", "switch": "switch", "for": "loop", "fork": "fork", "try": "try", "do": "group",
        "set": "set", "task": "task", "trigger": "trigger"}
UNIT_ID = r"(?:[A-Z]\d{1,4}[a-z]?)"
BRANCH_RE = re.compile(r"\b[a-z0-9-]+/(?:feat|fix|chore|docs|refactor|test|perf)/[a-z0-9-]+/[a-z0-9-]+")

esc = html.escape
WARN = []


def warn(msg):
    WARN.append(msg)


# ---------------------------------------------------------------- text helpers
def md_inline(s):
    s = esc(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def md(text):
    """Small Markdown subset: headings, nested lists, paragraphs, code spans."""
    out, para, lst = [], [], []

    def flush():
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para.clear()

    def close(to=-1):
        while lst and lst[-1][0] > to:
            out.append("</li></%s>" % lst.pop()[1])

    for raw in text.splitlines():
        line = raw.rstrip()
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if h:
            flush()
            close()
            lvl = min(len(h.group(1)) + 3, 6)
            out.append("<h%d>%s</h%d>" % (lvl, md_inline(h.group(2)), lvl))
        elif m:
            flush()
            ind, tag = len(m.group(1)), ("ol" if m.group(2)[0].isdigit() else "ul")
            close(ind)
            if lst and lst[-1][0] == ind and lst[-1][1] == tag:
                out.append("</li>")
            else:
                if lst and lst[-1][0] == ind:
                    out.append("</li></%s>" % lst.pop()[1])
                out.append("<%s>" % tag)
                lst.append([ind, tag])
            out.append("<li>" + md_inline(m.group(3)))
        elif not line.strip():
            flush()
            close()
        elif lst:
            out.append(" " + md_inline(line.strip()))
        else:
            para.append(line.strip())
    flush()
    close()
    return "\n".join(out)


def short(expr):
    """Mechanical shortening of a guard: `$accepted["a/b"] == true` -> `b accepted`."""
    s = re.sub(r"^\$\{\s*|\s*\}$", "", str(expr).strip())
    words = {("==", "true"): "accepted", ("!=", "true"): "not accepted", ("==", "false"): "failed",
             ("!=", "false"): "not failed", ("==", "null"): "not run", ("!=", "null"): "ran"}
    s = re.sub(r'\$accepted\["([^"]+)"\]\s*(==|!=)\s*(true|false|null)',
               lambda m: m.group(1).split("/")[-1] + " " + words[(m.group(2), m.group(3))], s)
    return s.replace("$context.", "").replace("$", "")


def human_dur(d):
    if not isinstance(d, dict):
        return str(d)
    return ", ".join("%s %s" % (v, k if v != 1 else k.rstrip("s")) for k, v in d.items())


def chain(role, roles):
    seq, seen = [role], {role}
    while role in roles and roles[role].get("escalates-to"):
        role = roles[role]["escalates-to"]
        if role in seen:
            break
        seq.append(role)
        seen.add(role)
    return seq


def target_text(tg):
    parts = []
    for k in ("at-most", "at-least"):
        if k in tg:
            parts.append("%s %s" % (k.replace("-", " "), tg[k]))
    if tg.get("per"):
        parts.append("per " + tg["per"])
    return " ".join(parts)


def ci_state(roll):
    st = [(c.get("conclusion") or c.get("status") or c.get("state") or "").upper() for c in roll or []]
    if not st:
        return "no checks"
    if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE") for s in st):
        return "failing"
    if any(s not in ("SUCCESS", "NEUTRAL", "SKIPPED") for s in st):
        return "running"
    return "passing"


# ---------------------------------------------------------------- org documents
def load_org(org_root):
    import yaml  # the workflows are YAML

    org_root = Path(org_root)
    org = {"wf": {}, "manifest": json.loads((org_root / "manifest.json").read_text()), "metrics": {}}
    for name in ("metrics.json", "metrics.research.json"):
        p = org_root / name
        if p.exists():
            for k, v in json.loads(p.read_text()).items():
                v["catalog"] = name
                org["metrics"][k] = v
    for p in sorted((org_root / "workflows").glob("*.yaml")):
        doc = yaml.safe_load(p.read_text())
        org["wf"][doc["document"]["name"]] = {"doc": doc, "path": "workflows/" + p.name, "tree": parse(doc["do"])}
    reads = {}
    readme = org_root / "checks/README.md"
    if readme.exists():
        for m in re.finditer(r"^\|\s*`([^`]+)`\s*\|\s*(\w+)\s*\|[^|]*\|\s*(.*?)\s*\|\s*$", readme.read_text(), re.M):
            reads[m.group(1)] = m.group(3)
    org["check_reads"] = reads
    return org


def kind_of(t, meta):
    for k in ("for", "fork", "try", "switch"):
        if k in t:
            return k
    if "listen" in t:
        return "gate" if meta.get("by") == "human" else "listen"
    for k in ("wait", "emit", "raise"):
        if k in t:
            return k
    if "run" in t:
        return "call" if "workflow" in t["run"] else "step"
    if "set" in t:
        return "set"
    if "do" in t:
        return "do"
    return "task"


def parse(items, prefix=""):
    out = []
    for it in items:
        (name, t), = it.items()
        meta = ((t.get("metadata") or {}).get("org") or {})
        n = {"name": name, "key": prefix + name, "kind": kind_of(t, meta), "t": t, "org": meta}
        if n["kind"] in ("for", "do"):
            n["children"] = parse(t["do"], n["key"] + "/")
        elif n["kind"] == "try":
            n["children"] = parse(t["try"], n["key"] + "/")
        elif n["kind"] == "fork":
            n["branches"] = [parse([b], n["key"] + "/") for b in t["fork"]["branches"]]
        out.append(n)
    return out


def walk(tree):
    for n in tree:
        yield n
        yield from walk(n.get("children", []))
        for b in n.get("branches", []):
            yield from walk(b)


def event_of(t, verb):
    try:
        if verb == "emit":
            return t["emit"]["event"]["with"]["type"]
        to = t["listen"]["to"]
        if "one" in to:
            return to["one"]["with"]["type"]
        return ", ".join(x["with"]["type"] for x in to.get("any", to.get("all", [])))
    except (KeyError, TypeError):
        return "?"


def start_type(doc):
    try:
        s = doc["schedule"]
        on = s["on"] if "on" in s else s[True]  # PyYAML reads the YAML 1.1 key `on` as True
        return on["one"]["with"]["type"]
    except (KeyError, TypeError):
        return None


def rubric(org_root, path):
    p = Path(org_root) / path
    if not p.exists():
        warn("rubric file missing: %s" % path)
        return path, []
    t = p.read_text()
    title = (re.search(r"^# (.*)$", t, re.M) or [None, path])[1]
    rules = []
    for line in t.split("## On a fail")[0].splitlines():
        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m:
            rules.append(m.group(2))
        elif rules and line.startswith(" ") and line.strip():
            rules[-1] += " " + line.strip()
    return title, rules


def is_floor(n, floors):
    return bool(n["org"].get("floor")) or n["name"] in floors


# ---------------------------------------------------------------- layout and work package
def load_layout(path):
    """Segments, components (id, name, files), workflow descriptions and inferred edges."""
    lay = json.loads(Path(path).read_text())
    return {"segments": lay.get("segments", []), "components": lay.get("components", []),
            "describe": lay.get("describe", {}), "inferred_edges": lay.get("inferred_edges", [])}


def load_site(wp):
    """The work package's site.json: unit_map, component_units, decisions. Empty without one."""
    out = {"unit_map": {}, "component_units": {}, "decisions": []}
    if wp and (Path(wp) / "site.json").is_file():
        d = json.loads((Path(wp) / "site.json").read_text())
        for k in out:
            if k in d:
                out[k] = d[k]
    return out


def _read(wp, rel):
    if not wp:
        return ""
    p = Path(wp) / rel
    return p.read_text() if p.is_file() else ""


def log_rows(wp):
    return [ln for ln in _read(wp, "run-log.md").splitlines() if re.match(r"^\|\s*\d{4}-", ln)]


def plan_section(text, head):
    m = re.search(r"^## %s[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(head), text, re.S | re.M)
    return m.group(1).strip() if m else ""


def plan_items(text, head):
    return [re.sub(r"^\d+\.\s+", "", ln) for ln in plan_section(text, head).splitlines() if re.match(r"^\d+\.\s", ln)]


def plans(wp):
    d = Path(wp) / "agent-plans" if wp else None
    return sorted(d.glob("*.md")) if d and d.is_dir() else []


def load_units(wp, rows):
    raw = _read(wp, "status-units.json")
    units = json.loads(raw) if raw else []
    for u in units:
        u["src"] = "status-units.json"
        u["acc"] = plan_items(_read(wp, "agent-plans/%s.md" % u["id"]), "Acceptance")
    known = {u["id"] for u in units}
    wave = {u["id"]: u["w"] for u in units}
    for p in plans(wp):
        uid = p.stem
        if uid in known:
            continue
        t = p.read_text()
        m = re.match(r"# Brief \S+: (.+)", t)
        name = re.sub(r"\s*\(.*\)$", "", m.group(1)) if m else uid
        name = name[0].upper() + name[1:]
        dm = re.search(r"Depends on:?([^\n]*)", t)
        dep = []
        for d in re.findall(r"\b(%s)\b" % UNIT_ID, dm.group(1) if dm else ""):
            if d not in dep and d != uid:
                dep.append(d)
        st, note, pr = "active", "building: no verified row in the run log yet", None
        for r in rows:
            if re.search(r"\b%s verified\b" % re.escape(uid), r):
                st, note = "done", "verified"
            pm = re.search(r"\b%s\b[^|]*?pushed as PR #(\d+)" % re.escape(uid), r)
            if pm:
                st, pr, note = "done", int(pm.group(1)), "verified, PR %s" % pm.group(1)
        obj = plan_section(t, "Objective").split("\n")[0]
        acc = plan_items(t, "Acceptance")
        w = max([wave.get(d, 1) for d in dep] or [0]) + 1
        wave[uid] = w
        units.append({"id": uid, "w": w, "name": name, "st": st, "note": note, "dep": dep, "what": obj,
                      "tgt": acc[0] if acc else "", "acc": acc, "src": "agent-plans/%s.md" % uid, "log_pr": pr})
    return units


def followups(wp, rows):
    """Units with a follow-up sent in the run log and no later 'verified', 'reported' or 'pushed' row."""
    out = {}
    for i, r in enumerate(rows):
        m = re.search(r"Follow-ups sent to ((?:%s(?:, | and )?)+)" % UNIT_ID, r)
        if not m:
            continue
        f = re.search(r"findings/(followups-update-([\d-]+)\.md)", r)
        n = f.group(2) if f else "?"
        ftext = _read(wp, "findings/" + f.group(1)) if f else ""
        for uid in re.findall(UNIT_ID, m.group(1)):
            pat = r"\b%s update-%s follow-up\b[^|]*?\b(verified|reported|pushed)\b" % (uid, n)
            if any(re.search(pat, r2) for r2 in rows[i + 1:]):
                continue
            sm = re.search(r"^## %s \([^)]*\):\s*(.*)$" % uid, ftext, re.M)
            out[uid] = {"n": n, "label": "update %s follow-up" % n, "file": "findings/" + f.group(1) if f else None,
                        "text": sm.group(1) if sm else "See the follow-up file."}
    for i, r in enumerate(rows):
        for uid, n in re.findall(r"findings/(%s)-followup-(\d+)\.md" % UNIT_ID, r):
            pat = r"\b%s follow-up %s\b[^|]*?\b(verified|reported|pushed)\b" % (uid, n)
            if uid in out or any(re.search(pat, r2) for r2 in rows[i + 1:]):
                continue
            out[uid] = {"n": n, "label": "follow-up %s" % n, "file": "findings/%s-followup-%s.md" % (uid, n),
                        "text": "Close the gaps listed in the follow-up file."}
    return out


def branches(wp):
    """Unit id to the first branch name its agent plan names."""
    out = {}
    for p in plans(wp):
        m = BRANCH_RE.search(p.read_text())
        if m:
            out[p.stem] = m.group(0)
    return out


def findings(wp):
    d = Path(wp) / "findings" if wp else None
    return sorted(f.name for f in d.glob("*.md")) if d and d.is_dir() else []
