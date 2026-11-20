#!/usr/bin/env python3
"""Check spec-check. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

REQUIRED = ("title", "valid_inputs", "expected_outputs", "failure_definition", "performance",
            "dependencies", "out_of_scope")


def check(ev):
    item = ev["item"]
    problems = [f"{k} is empty or missing" for k in REQUIRED
                if not (isinstance(item.get(k), str) and item[k].strip())]
    criteria = item.get("criteria") or []
    if not criteria:
        problems.append("criteria is empty")
    ids = [c.get("id") for c in criteria]
    if len(ids) != len(set(ids)):
        problems.append("criteria ids are not unique")
    problems += [f"criterion {c.get('id')} has no text" for c in criteria if not str(c.get("text", "")).strip()]
    return problems


if __name__ == "__main__":
    _lib.run(check)
