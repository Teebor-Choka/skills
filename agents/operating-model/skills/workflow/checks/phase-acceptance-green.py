#!/usr/bin/env python3
"""Check phase-acceptance-green. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    data = ev.out()
    problems = _lib.green_problems(data)
    faults = [k for k in ("layer_fault", "system_fault") if k in data]
    if len(faults) != 1 or data[faults[0]] not in ("none", "unit", "design", "spec"):
        problems.append("name exactly one of layer_fault and system_fault, one of none, unit, design, spec")
    elif data[faults[0]] != "none":
        problems.append(f"{faults[0]} is {data[faults[0]]!r}: a declared test failed")
    expected = data["expected_count"]
    s = data["suite"]
    if not _lib.is_int(expected) or expected <= 0:
        problems.append("expected_count must be a positive integer")
    elif _lib.is_int(s.get("passed")) and _lib.is_int(s.get("failed")) and s["passed"] + s["failed"] < expected:
        problems.append(f"the suite shrank: {s['passed'] + s['failed']} tests run, {expected} expected")
    return problems

if __name__ == "__main__":
    _lib.run(check)
