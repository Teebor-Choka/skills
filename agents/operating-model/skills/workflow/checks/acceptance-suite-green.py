#!/usr/bin/env python3
"""Check acceptance-suite-green. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(data):
    problems = _lib.green_problems(data)
    expected = data["expected_count"]
    if not _lib.is_int(expected) or expected <= 0:
        return problems + ["expected_count must be a positive integer"]
    s = data["suite"]
    if isinstance(s, dict) and _lib.is_int(s.get("passed")) and _lib.is_int(s.get("failed")) \
            and s["passed"] + s["failed"] < expected:
        problems.append(f"the suite shrank: {s['passed'] + s['failed']} tests run, {expected} expected")
    return problems


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
