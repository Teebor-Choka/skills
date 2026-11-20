"""Classify a change to an org root by rung (spec section 10).

    check_change(base, new, rungs) -> (entries, refused)

`base` and `new` map an org-root-relative path to the file's bytes, or None for an absent file, and hold every
file under the org root. `rungs` is the set of rungs the proposer may apply without a signature. `entries` holds
one `(path, task path or "", row, rung)` per change found; `refused` holds the entries whose rung is not in
`rungs`. The change is refused when `refused` is not empty.

Rungs, lowest first: free < ordinary < protected < frozen. A change that matches several rows takes the highest.
Fail closed: a file that cannot be loaded or a workflow whose tasks cannot be paired is frozen, and so is every
file whose class depends on what the unreadable document says (floors, targets, catalog).

The grammar (kind table, accepted subset, the spec) is frozen too but lives outside the org root, so a map of
org-root files never holds it.
"""
import json
import os
import re
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_catalog as vc  # noqa: E402
import validate_org as vo  # noqa: E402

FREE, ORDINARY, PROTECTED, FROZEN = "free", "ordinary", "protected", "frozen"
MISSING = object()

R_MANIFEST = "manifest"
R_FLOOR_TASK = "floor task"
R_FLOOR_POS = "floor position"
R_REMOVE_CARRIER = "removing a task with acceptance or metrics"
R_REMOVE_TASK = "removing a task"
R_REMOVE_ITEM = "removing a metrics entry or acceptance item"
R_WEAKEN = "weakening an acceptance item"
R_CRITERIA = "criteria content"
R_CATALOG_EXPOSED = "catalog entry targeted or floor-listed"
R_FLOOR_FILE = "file named by a floor task"
R_COLLECTOR = "collector of a targeted or floor-listed metric"
R_ADD_TASK = "adding a task"
R_REORDER = "reordering tasks"
R_KEYS = "by, role, to, brief, run or policy"
R_ADD_ITEM = "adding a metric or acceptance item"
R_RAISE = "raising a sample"
R_FLOW = "if, while, then or switch case"
R_BOUND = "loop bound, retry count or timeout"
R_CATALOG = "catalog entry"
R_CATALOG_NEW = "adding a catalog entry no workflow or target names"
R_OTHER_FILE = "other file under the org root"
R_NO_ROW = "no row names it"
R_BRIEF = "brief content"
R_STACK = "stack document"
R_BAD = "unloadable document"
R_BAD_PATH = "path is not a relative path under the org root"
R_UNSURE = "depends on a document that did not load"
R_WF_FILE = "workflow file added or removed"

CATALOG_FILE = re.compile(r"^metrics[^/]*\.(yaml|yml|json)$")
MANIFEST_FILES = ("manifest.yaml", "manifest.yml", "manifest.json")
WORKFLOW_SUFFIXES = (".yaml", ".yml", ".json")
CHILDREN = "<children>"


def _canon(v):
    """Canonical text of a loaded value: key order is ignored, 1 / 1.0 / true stay different."""
    return json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _map(v):
    return v if isinstance(v, dict) else {}


def _bytes(v):
    if v is None or isinstance(v, bytes):
        return v
    if isinstance(v, (bytearray, memoryview)):
        return bytes(v)
    if isinstance(v, str):
        return v.encode("utf-8")
    raise TypeError(f"file content must be bytes or None, not {type(v).__name__}")


# ---------------------------------------------------------------- loading


def _load(path, data):
    """Return (document, error). Reuses the spec 2.1 loader through a temporary file."""
    ext = os.path.splitext(path)[1] or ".json"
    with tempfile.TemporaryDirectory() as tmp:
        name = os.path.join(tmp, "doc" + ext)
        with open(name, "wb") as f:
            f.write(data)
        try:
            doc = vo.load_file(name)
        except (vo.LoadError, vo.UsageError) as e:
            return None, str(e).replace(name, path)
    errs = vo._value_errors(doc)
    if errs:
        return None, f"{path}: {errs[0]}"
    return doc, None


def _names(lst):
    return [next(iter(i)) if isinstance(i, dict) and len(i) == 1 else None for i in lst]


def _own(task, children):
    """The task with its child task lists replaced by children(list)."""
    t = dict(task)
    if isinstance(t.get("do"), list):
        t["do"] = children(t["do"])
    fork = t.get("fork")
    if isinstance(fork, dict) and isinstance(fork.get("branches"), list):
        t["fork"] = {**fork, "branches": children(fork["branches"])}
    if isinstance(t.get("try"), list):
        t["try"] = children(t["try"])
        catch = t.get("catch")
        if isinstance(catch, dict) and isinstance(catch.get("do"), list):
            t["catch"] = {**catch, "do": children(catch["do"])}
    return t


def _flat(task):
    return json.loads(_canon(_own(task, lambda lst: CHILDREN)))


def _list_key(node):
    parent = node["parent"]
    if parent is None:
        return ("", "do")
    t = parent["task"]
    lists = {"do": t.get("do"), "branches": _map(t.get("fork")).get("branches"), "try": t.get("try"),
             "catch": _map(t.get("catch")).get("do")}
    for k, lst in lists.items():
        if lst is not None and id(lst) == node["list"]:
            return (parent["path"], k)
    return (parent["path"], "?")


def _workflow(doc):
    """Return ({path: node}, error). A document whose tasks cannot be paired is an error."""
    if not isinstance(doc, dict) or not isinstance(doc.get("do"), list):
        return None, "workflow must be a map with a 'do' list"
    errs, nodes = [], []
    try:
        vo._walk(doc["do"], "", 1, errs, nodes, None)
    except vo._TooManyTasks as e:
        return None, f"{e}: too many tasks"
    if errs:
        return None, errs[0]
    out = {}
    for n in nodes:
        kind = n["kind"]
        if kind is None or kind == "badrun" or str(kind).startswith("refused"):
            return None, f"{n['path']}: task form cannot be walked"
        if n["path"] in out:
            return None, f"{n['path']}: duplicate task path"
        n["flat"] = _canon(_flat(n["task"]))
        n["full"] = _canon(_own(n["task"], _names))
        n["listkey"] = _list_key(n)
        out[n["path"]] = n
    return out, None


# ---------------------------------------------------------------- task facts


def _org(task):
    return _map(_map(task.get("metadata")).get("org"))


def _floor_call(task, manifest):
    name = _map(_map(task.get("run")).get("workflow")).get("name")
    entry = _map(_map(manifest.get("workflows")).get(name)) if isinstance(name, str) else {}
    floors = entry.get("floors")
    return isinstance(floors, list) and bool(floors)


def _is_floor(task, manifest):
    return _org(task).get("floor") is True or _floor_call(task, manifest)


def _carries(task):
    o = _org(task)
    return any(isinstance(o.get(k), list) and o[k] for k in ("acceptance", "metrics"))


def _floor_names(task):
    """Files and metrics a floor task names: (paths, metrics)."""
    o = _org(task)
    paths = set()
    acceptance = o.get("acceptance")
    for item in acceptance if isinstance(acceptance, list) else []:
        c = _map(item).get("check")
        if isinstance(c, str):
            paths.add(f"checks/{c}.py")
    for side in ("input", "output"):
        ep = _map(_map(_map(task.get(side)).get("schema")).get("resource")).get("endpoint")
        if isinstance(ep, str):
            paths.add(ep)
    cmd = _map(_map(task.get("run")).get("shell")).get("command")
    if isinstance(cmd, str) and cmd != "agent-run":
        paths.add(f"bin/{cmd}")
    metrics = o.get("metrics")
    return paths, {m for m in metrics if isinstance(m, str)} if isinstance(metrics, list) else set()


# ---------------------------------------------------------------- task-level changes


def _pop(d, path):
    cur = d
    for k in path[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return MISSING
        cur = cur[k]
    if isinstance(cur, dict) and path[-1] in cur:
        return cur.pop(path[-1])
    return MISSING


def _same(a, b):
    if a is MISSING or b is MISSING:
        return a is b
    return _canon(a) == _canon(b)


def _list_shape(b, n):
    """Rows for a list that is added, removed or unreadable; None when both are lists."""
    if b is MISSING:
        return [(R_ADD_ITEM, PROTECTED)] if isinstance(n, list) else [(R_BAD, FROZEN)]
    if not isinstance(b, list) or (n is not MISSING and not isinstance(n, list)):
        return [(R_BAD, FROZEN)]
    if n is MISSING:
        return [(R_REMOVE_ITEM, FROZEN)]
    return None


def _metrics_change(b, n):
    if _same(b, n):
        return []
    rows = _list_shape(b, n)
    if rows is not None:
        return rows
    bc, nc = Counter(map(_canon, b)), Counter(map(_canon, n))
    out = []
    if bc - nc:
        out.append((R_REMOVE_ITEM, FROZEN))
    if nc - bc:
        out.append((R_ADD_ITEM, PROTECTED))
    return out or [(R_NO_ROW, PROTECTED)]


def _sample(item):
    """The effective sample of an item: absent means 1; None when it cannot be compared."""
    if not isinstance(item, dict):
        return None
    if "sample" not in item:
        return 1
    s = item["sample"]
    return s if isinstance(s, (int, float)) and not isinstance(s, bool) else None


def _without_sample(item):
    return _canon({k: v for k, v in item.items() if k != "sample"})


def _acceptance_change(b, n):
    if _same(b, n):
        return []
    rows = _list_shape(b, n)
    if rows is not None:
        return rows
    left_n, left_b = list(n), []
    for item in b:  # drop exact matches
        for i, cand in enumerate(left_n):
            if _canon(cand) == _canon(item):
                del left_n[i]
                break
        else:
            left_b.append(item)
    if not left_b and not left_n:
        return [(R_NO_ROW, PROTECTED)]  # same items, new order: item indices name rubric verdicts
    out, raised, unmatched = [], False, []
    for item in left_b:
        sb = _sample(item)
        for i, cand in enumerate(left_n):
            sn = _sample(cand)
            if sb is not None and sn is not None and _without_sample(item) == _without_sample(cand) and sn > sb:
                del left_n[i]
                raised = True
                break
        else:
            unmatched.append(item)
    if raised:
        out.append((R_RAISE, PROTECTED))
    if unmatched:
        out.append((R_WEAKEN if left_n else R_REMOVE_ITEM, FROZEN))
        left_n = left_n[len(unmatched):]
    if left_n:
        out.append((R_ADD_ITEM, PROTECTED))
    return out


def _task_changes(btask, ntask):
    """Rows for a paired task that is not a floor. Each differing area is one row."""
    b, n = _flat(btask), _flat(ntask)
    out = []

    def both(path):
        return _pop(b, path), _pop(n, path)

    out += _metrics_change(*both(("metadata", "org", "metrics")))
    out += _acceptance_change(*both(("metadata", "org", "acceptance")))
    for group, row, rung in (
        ([("metadata", "org", k) for k in ("by", "role", "to", "brief", "policy")] + [("run",)], R_KEYS, PROTECTED),
        ([(k,) for k in ("if", "then", "while", "switch")], R_FLOW, PROTECTED),
        ([("timeout",), ("catch", "retry", "limit", "attempt", "count")], R_BOUND, ORDINARY),
    ):
        for path in group:
            bv, nv = both(path)
            if not _same(bv, nv):
                out.append((row, rung))
    bv, nv = both(("for", "in"))
    if not _same(bv, nv):
        extension = (isinstance(bv, list) and isinstance(nv, list) and len(bv) != len(nv)
                     and _canon(bv[:len(nv)]) == _canon(nv[:len(bv)]))
        out.append((R_BOUND, ORDINARY) if extension else (R_NO_ROW, PROTECTED))
    if _canon(b) != _canon(n):
        out.append((R_NO_ROW, PROTECTED))
    return out


# ---------------------------------------------------------------- the check


def _parse_all(paths, base, new, is_workflow):
    """Parse every manifest and workflow of both versions, changed or not."""
    unsure = False
    manifests, docs, bad_docs = {}, {}, {}
    for ver, files in (("base", base), ("new", new)):
        manifests[ver] = {}
        mpath = next((m for m in MANIFEST_FILES if files.get(m) is not None), None)
        if mpath:
            doc, err = _load(mpath, files[mpath])
            if err or not isinstance(doc, dict):
                unsure = True
            else:
                manifests[ver] = doc
        for p in paths:
            if is_workflow(p) and files.get(p) is not None:
                doc, err = _load(p, files[p])
                nodes, err = (None, err) if err else _workflow(doc)
                if err:
                    bad_docs[(ver, p)] = err
                    unsure = True
                else:
                    docs[(ver, p)] = (doc, nodes)
    return manifests, docs, bad_docs, unsure


def _catalogs(paths, base, new):
    """Merge each version's catalog files. Returns (merged by version, file of each entry, bad)."""
    merged_by, where, bad = {}, {}, False
    for ver, files in (("base", base), ("new", new)):
        loaded = []
        for p in paths:
            if CATALOG_FILE.match(p) and files.get(p) is not None:
                doc, err = _load(p, files[p])
                if err or not isinstance(doc, dict):
                    bad = bad or base.get(p) != new.get(p)
                    continue
                loaded.append((p, doc))
        merged, errs = vo.merge_catalogs(loaded)
        bad = bad or bool(errs)
        merged_by[ver] = merged
        for p, doc in loaded:
            for name in doc:
                where.setdefault((ver, name), p)
    return merged_by, where, bad


def check_change(base, new, rungs):
    base = {p: _bytes(v) for p, v in base.items()}
    new = {p: _bytes(v) for p, v in new.items()}
    rungs = set(rungs)
    entries = []

    def emit(path, task, row, rung):
        entries.append((path, task, row, rung))

    paths = sorted(set(base) | set(new))
    for p in [p for p in paths if not vc.relative_path_ok(p, "", ("",))]:
        if base.get(p) != new.get(p):
            emit(p, "", R_BAD_PATH, FROZEN)
        paths.remove(p)

    def is_workflow(p):
        return p.startswith("workflows/") and p.endswith(WORKFLOW_SUFFIXES)

    manifests, docs, bad_docs, unsure = _parse_all(paths, base, new, is_workflow)
    catalogs, catalog_file, catalog_bad = _catalogs(paths, base, new)
    unsure = unsure or catalog_bad

    floor_paths, floor_metrics, named_metrics = set(), set(), set()
    for (ver, _), (_, nodes) in docs.items():
        for n in nodes.values():
            metrics = _org(n["task"]).get("metrics")
            if isinstance(metrics, list):
                named_metrics.update(m for m in metrics if isinstance(m, str))
            if _is_floor(n["task"], manifests[ver]):
                fp, fm = _floor_names(n["task"])
                floor_paths |= fp
                floor_metrics |= fm
    targeted = set()
    for m in manifests.values():
        if isinstance(m.get("targets"), dict):
            targeted |= set(m["targets"])
    exposed = floor_metrics | targeted
    exposed_collectors = {c for cat in catalogs.values() for name in exposed
                          if isinstance(c := _map(cat.get(name)).get("collector"), str)}

    for p in paths:
        if base.get(p) == new.get(p):
            continue
        if p in MANIFEST_FILES:
            emit(p, "", R_MANIFEST, FROZEN)
        elif p == "stack.yaml":
            emit(p, "", R_STACK, FREE)
        elif CATALOG_FILE.match(p):
            if catalog_bad:
                emit(p, "", R_BAD, FROZEN)
        elif is_workflow(p):
            _workflow_entries(p, docs, bad_docs, manifests, emit)
        elif p.startswith("briefs/") and p.endswith(".md"):
            emit(p, "", R_BRIEF, FREE)
        elif p.startswith("criteria/") and p.endswith(".md"):
            emit(p, "", R_CRITERIA, FROZEN)
        elif p.startswith(("checks/", "schemas/", "bin/", "collectors/")):
            named = p in floor_paths or p in exposed_collectors
            if unsure:
                emit(p, "", R_UNSURE, FROZEN)
            elif named:
                emit(p, "", R_COLLECTOR if p.startswith("collectors/") else R_FLOOR_FILE, FROZEN)
            else:
                emit(p, "", R_OTHER_FILE, PROTECTED)
        else:
            emit(p, "", R_OTHER_FILE, PROTECTED)

    if not catalog_bad and any(CATALOG_FILE.match(p) and base.get(p) != new.get(p) for p in paths):
        for name in sorted(set(catalogs["base"]) | set(catalogs["new"])):
            b, n = catalogs["base"].get(name, MISSING), catalogs["new"].get(name, MISSING)
            if _same(b, n):
                continue
            where = catalog_file.get(("new", name)) or catalog_file.get(("base", name))
            if unsure or name in exposed:
                emit(where, "", f"{R_CATALOG_EXPOSED}: {name}", FROZEN)
            elif b is MISSING and name not in named_metrics:
                emit(where, "", f"{R_CATALOG_NEW}: {name}", ORDINARY)
            else:
                emit(where, "", f"{R_CATALOG}: {name}", PROTECTED)

    return entries, [e for e in entries if e[3] not in rungs]


def _workflow_entries(p, docs, bad_docs, manifests, emit):
    if bad_docs.get(("base", p)) or bad_docs.get(("new", p)):
        emit(p, "", R_BAD, FROZEN)
        return
    bdoc, bnodes = docs.get(("base", p), (None, {}))
    ndoc, nnodes = docs.get(("new", p), (None, {}))
    if bdoc is None or ndoc is None:
        emit(p, "", R_WF_FILE, PROTECTED)
    else:
        for k in sorted(set(bdoc) | set(ndoc)):
            bv, nv = bdoc.get(k, MISSING), ndoc.get(k, MISSING)
            if k == "do" or _same(bv, nv):
                continue
            row = R_NO_ROW
            if k == "document":
                bd = json.loads(_canon(bv)) if bv is not MISSING else {}
                nd = json.loads(_canon(nv)) if nv is not MISSING else {}
                pb, pn = _pop(bd, ("metadata", "org", "policy")), _pop(nd, ("metadata", "org", "policy"))
                if _canon(bd) == _canon(nd) and not _same(pb, pn):
                    row = R_KEYS
            emit(p, "", row, PROTECTED)

    mb, mn = manifests["base"], manifests["new"]

    def floor_in(path):
        return ((path in bnodes and _is_floor(bnodes[path]["task"], mb))
                or (path in nnodes and _is_floor(nnodes[path]["task"], mn)))

    for path, node in bnodes.items():
        if path in nnodes:
            continue
        if floor_in(path):
            emit(p, path, R_FLOOR_TASK, FROZEN)
        elif _carries(node["task"]):
            emit(p, path, R_REMOVE_CARRIER, FROZEN)
        else:
            emit(p, path, R_REMOVE_TASK, PROTECTED)
    for path in nnodes:
        if path not in bnodes:
            emit(p, path, *((R_FLOOR_TASK, FROZEN) if floor_in(path) else (R_ADD_TASK, PROTECTED)))

    common = [path for path in bnodes if path in nnodes]
    for path in common:
        if bnodes[path]["flat"] == nnodes[path]["flat"]:
            continue
        if floor_in(path):
            emit(p, path, R_FLOOR_TASK, FROZEN)
        else:
            for row, rung in _task_changes(bnodes[path]["task"], nnodes[path]["task"]):
                emit(p, path, row, rung)

    # Reordering: the order of the tasks both versions hold, list by list.
    seqs = {}
    for ver, nodes in (("b", bnodes), ("n", nnodes)):
        for path in sorted(common, key=lambda q: nodes[q]["order"]):
            seqs.setdefault((ver, nodes[path]["listkey"]), []).append(path)
    for key in sorted({k for _, k in seqs}):
        if seqs.get(("b", key)) != seqs.get(("n", key)):
            emit(p, key[0], R_REORDER, PROTECTED)

    # Floor position (review 2, N6): ancestors unchanged, and the same tasks after the floor.
    for path in common:
        if not floor_in(path):
            continue
        bn, nn = bnodes[path], nnodes[path]
        anc, a = [], bn["parent"]
        while a:
            anc.append(a["path"])
            a = a["parent"]
        ancestors_same = all(bnodes[q]["full"] == nnodes[q]["full"] for q in anc)
        after_b = {q for q in common if bnodes[q]["order"] > bn["order"]}
        after_n = {q for q in common if nnodes[q]["order"] > nn["order"]}
        if not (ancestors_same and after_b == after_n):
            emit(p, path, R_FLOOR_POS, FROZEN)
