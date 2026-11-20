#!/usr/bin/env python3
"""Check acceptance-suite-green. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    problems = _lib.green_problems(ev.out())
    recorded = ev.fact("acceptance-red")["runs"]
    if not (isinstance(recorded, list) and recorded):
        return problems + ["the red run of the acceptance suite recorded no tests"]
    s = ev.out()["suite"]
    if isinstance(s, dict) and _lib.is_int(s.get("passed")) and _lib.is_int(s.get("failed")) \
            and s["passed"] + s["failed"] < len(recorded):
        problems.append(f"the suite shrank: {s['passed'] + s['failed']} tests run, {len(recorded)} ran red")
    return problems


if __name__ == "__main__":
    _lib.run(check)
