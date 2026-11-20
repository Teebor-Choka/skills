#!/usr/bin/env python3
"""Check spec-coverage. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    covered = {c for t in ev["tests"] for c in t["criteria"]}
    return [f"criterion {c['id']} has no acceptance test" for c in ev["item"]["criteria"]
            if c["id"] not in covered]


if __name__ == "__main__":
    _lib.run(check)
