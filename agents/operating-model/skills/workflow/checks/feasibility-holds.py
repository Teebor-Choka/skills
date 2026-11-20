#!/usr/bin/env python3
"""Check feasibility-holds. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    data = ev.out()
    failed, reasons = data["failed"], data["reasons"]
    if not (isinstance(failed, list) and all(_lib.is_str(f) for f in failed)):
        return ["failed must be a list of dimension names"]
    if not (isinstance(reasons, list) and reasons and all(_lib.is_str(r) for r in reasons)):
        return ["reasons must be a non-empty list of strings"]
    if data["feasible"] is not True:
        return [f"the design is not feasible: {', '.join(failed) or 'no dimension named'}"]
    if failed:
        return ["feasible is true but a dimension failed: " + ", ".join(failed)]
    return []

if __name__ == "__main__":
    _lib.run(check)
