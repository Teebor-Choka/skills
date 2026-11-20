#!/usr/bin/env python3
"""Check every-acceptance-test-fails-on-an-assertion. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    claimed = [t["id"] for t in ev.claim("acceptance-tests")["tests"]]
    return _lib.assertion_failures(ev.out()["runs"], claimed)


if __name__ == "__main__":
    _lib.run(check)
