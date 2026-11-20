#!/usr/bin/env python3
"""Check checks-green-and-gate-approved. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    problems = []
    if ev["ci"]["state"] != "success":
        problems.append(f"checks are '{ev['ci']['state']}', not success")
    if ev["gate"]["decision"] != "approve":
        problems.append(f"merge-gate decision is '{ev['gate']['decision']}', not approve")
    return problems


if __name__ == "__main__":
    _lib.run(check)
