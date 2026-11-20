#!/usr/bin/env python3
"""Check failing-test-committed. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(data):
    runs, files, dirty = data["runs"], data["files"], data["uncommitted"]
    if not (_lib.is_str(data["head"]) and _lib.is_str(data["base"])):
        return ["head and base must be commit ids"]
    if not (isinstance(files, list) and all(_lib.is_str(f) for f in files) and isinstance(dirty, list)
            and all(_lib.is_str(f) for f in dirty)):
        return ["files and uncommitted must be lists of paths"]
    problems = []
    if data["committed"] is not True or dirty or not files:
        problems.append("the failing test is not committed: " + (", ".join(dirty) if dirty else "no test file was added"))
    if data["head"] == data["base"]:
        problems.append("head equals base: nothing was committed since the bug was reported")
    if not isinstance(runs, list) or not runs:
        return problems + ["no reproducing test ran"]
    for r in runs:
        if not (isinstance(r, dict) and _lib.is_str(r.get("test")) and _lib.is_str(r.get("outcome"))):
            return problems + ["each run needs a test id and an outcome"]
        if r["outcome"] != "assertion":
            problems.append(f"{r['test']}: the reproducing test ended with '{r['outcome']}', not an assertion failure")
    return problems

if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
