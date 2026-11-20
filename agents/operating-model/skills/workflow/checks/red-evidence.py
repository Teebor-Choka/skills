#!/usr/bin/env python3
"""Check red-evidence. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    out = ev.out()
    problems = _lib.assertion_failures(out["runs"], missing_symbol_ok=ev.new_symbols())
    write_set = ev.write_set()
    changed = out["changed"]
    if not (isinstance(changed, list) and all(isinstance(p, str) for p in changed)):
        return problems + ["changed must be a list of paths"]
    # P57: red writes tests only; production files of the write_set must still equal the base
    problems += [f"production file changed at red: {p} (restore it to the base; red writes only tests)"
                 for p in changed if _lib.in_write_set(p, write_set) and not _lib.TEST_FILE.search(p)]
    return problems


if __name__ == "__main__":
    _lib.run(check)
