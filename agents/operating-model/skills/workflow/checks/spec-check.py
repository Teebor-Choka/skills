#!/usr/bin/env python3
"""Check spec-check. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import re

CATEGORIES = ("title", "valid_inputs", "expected_outputs", "failure_definition", "performance",
              "dependencies", "out_of_scope", "ai_gap")
EMPTY = {"n/a", "na", "none", "tbd", "todo", "-"}


def blank(v):
    return not _lib.is_str(v) or v.strip().lower().rstrip(".") in EMPTY


def check(ev):
    item = ev.out()
    problems = [f"{k} is empty, missing or a placeholder" for k in CATEGORIES if blank(item.get(k))]
    criteria = item.get("criteria")
    if not (isinstance(criteria, list) and criteria):
        return problems + ["criteria is empty or not a list"]
    ids = []
    for i, c in enumerate(criteria):
        if not isinstance(c, dict):
            problems.append(f"criterion {i} is not a map")
            continue
        cid = c.get("id")
        if not (isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9-]+", cid)):
            problems.append(f"criterion {i} has no valid id")
        ids.append(cid)
        if blank(c.get("text")):
            problems.append(f"criterion {cid} has no text")
    if len(ids) != len(set(ids)):
        problems.append("criteria ids are not unique")
    return problems


if __name__ == "__main__":
    _lib.run(check)
