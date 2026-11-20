#!/usr/bin/env python3
"""Check every-proposal-is-within-its-rung. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    allowed = set(ev["allowed_rungs"])
    return [f"proposal {p['id']} needs rung '{p['rung']}', allowed: {sorted(allowed)}"
            for p in ev["proposals"] if p["rung"] not in allowed]


if __name__ == "__main__":
    _lib.run(check)
