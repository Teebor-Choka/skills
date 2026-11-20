#!/usr/bin/env python3
"""Check spec-coverage. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    ids = [c["id"] for c in ev.claim("spec")["criteria"]]
    tests = ev.out()["tests"]
    if not (isinstance(tests, list) and tests):
        return ["no acceptance tests listed"]
    problems, covered = [], set()
    for t in tests:
        crit = t["criteria"]
        if not (_lib.is_str(t["id"]) and isinstance(crit, list) and all(isinstance(c, str) for c in crit)):
            return ["each test needs an id and a list of criterion ids"]
        problems += [f"test {t['id']} names unknown criterion {c}" for c in crit if c not in ids]
        covered.update(crit)
    problems += [f"criterion {c} has no acceptance test" for c in ids if c not in covered]
    return problems


if __name__ == "__main__":
    _lib.run(check)
