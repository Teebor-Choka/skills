#!/usr/bin/env python3
"""Check write-sets-are-disjoint. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import posixpath
import re

LOCKED_DIRS = {"checks", "criteria", "bin", "collectors"}
LOCKED_STEMS = ("manifest", "metrics")  # manifest.* and metrics*.* catalogs, any case, json or yaml
LOCKED_EXT = (".json", ".yaml", ".yml")


def parts(path):
    """Lower-cased path components, or None when the path is not a plain relative path."""
    if not isinstance(path, str) or not path.strip() or path.startswith("/") or re.search(r"[*?\[\]{}\\]", path):
        return None
    if ".." in path.split("/"):
        return None
    norm = posixpath.normpath(path)
    return None if norm == "." else tuple(norm.lower().split("/"))


def overlap(a, b):
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def locked(p, tests):
    top = len(p) == 1 and p[0].endswith(LOCKED_EXT) and p[0].startswith(LOCKED_STEMS)
    return p[0] in LOCKED_DIRS or top or any(overlap(p, t) for t in tests)


def has_cycle(deps):
    state = {}

    def visit(u):
        if state.get(u) == 1:
            return True
        if state.get(u) == 2:
            return False
        state[u] = 1
        if any(visit(v) for v in deps[u]):
            return True
        state[u] = 2
        return False

    return any(visit(u) for u in deps)


def check(ev):
    units = ev.out()["units"]
    if not (isinstance(units, list) and units):
        return ["the cut has no units"]
    claimed = ev.claim("acceptance-tests")["tests"]
    if not isinstance(claimed, list):
        return ["the acceptance tests output must list tests"]
    tests = [parts(t.get("path")) for t in claimed]
    if not tests or None in tests:
        return ["every acceptance test needs a plain relative path"]
    criteria = {c["id"] for c in ev.claim("spec")["criteria"]}
    problems, owned, deps = [], [], {}
    ids = [u["id"] for u in units]
    if len(ids) != len(set(ids)):
        problems.append("unit ids are not unique")
    for u in units:
        uid = u["id"]
        ws = u["write_set"]
        if not (isinstance(ws, list) and ws):
            problems.append(f"unit {uid} has an empty write-set")
            continue
        for raw in ws:
            p = parts(raw)
            if p is None:
                problems.append(f"unit {uid}: write-set path {raw!r} is empty, absolute, a glob or has '..'")
            elif locked(p, tests):
                problems.append(f"unit {uid}: write-set path {raw!r} covers a protected file")
            else:
                owned.append((uid, raw, p))
        crit = u["criteria"]
        if not (isinstance(crit, list) and crit):
            problems.append(f"unit {uid} serves no criterion")
        else:
            problems += [f"unit {uid} names unknown criterion {c}" for c in crit if c not in criteria]
        deps[uid] = u.get("depends_on", [])
        if not isinstance(deps[uid], list):
            return problems + [f"unit {uid}: depends_on must be a list"]
    for uid, d in deps.items():
        problems += [f"unit {uid} depends on unknown unit {x}" for x in d if x not in deps]
    if not problems and has_cycle(deps):
        problems.append("depends_on has a cycle")
    for i, (u1, r1, p1) in enumerate(owned):
        for u2, r2, p2 in owned[i + 1:]:
            if u1 != u2 and overlap(p1, p2):
                problems.append(f"units {u1} and {u2} both write {r1} / {r2}")
    return problems


if __name__ == "__main__":
    _lib.run(check)
