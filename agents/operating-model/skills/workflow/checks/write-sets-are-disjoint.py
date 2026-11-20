#!/usr/bin/env python3
"""Check write-sets-are-disjoint. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def overlap(a, b):
    if a == b:
        return True
    return (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


def check(ev):
    units = ev["units"]
    problems = [f"unit {u['id']} has an empty write-set" for u in units if not u["write_set"]]
    for i, u in enumerate(units):
        for v in units[i + 1:]:
            for a in u["write_set"]:
                for b in v["write_set"]:
                    if overlap(a, b):
                        problems.append(f"units {u['id']} and {v['id']} both write {a} / {b}")
    return problems


if __name__ == "__main__":
    _lib.run(check)
