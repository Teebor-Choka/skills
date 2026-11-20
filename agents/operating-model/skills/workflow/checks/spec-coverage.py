#!/usr/bin/env python3
"""Check spec-coverage. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def ids_of(item):
    return [c["id"] for c in item["criteria"]]


def check(data):
    ids = ids_of(data["item"])
    problems = []
    if sorted(ids) != sorted(data["spec_criteria_ids"]):
        problems.append("the item differs from the criteria ids of the spec step")
    tests = data["tests"]
    if not (isinstance(tests, list) and tests):
        return problems + ["no acceptance tests recorded"]
    covered = set()
    for t in tests:
        crit = t["criteria"]
        if not (_lib.is_str(t["id"]) and isinstance(crit, list) and all(isinstance(c, str) for c in crit)):
            return problems + ["each test needs an id and a list of criterion ids"]
        problems += [f"test {t['id']} names unknown criterion {c}" for c in crit if c not in ids]
        covered.update(crit)
    problems += [f"criterion {c} has no acceptance test" for c in ids if c not in covered]
    return problems


if __name__ == "__main__":
    _lib.run(check, self_step=False, parse=True)
