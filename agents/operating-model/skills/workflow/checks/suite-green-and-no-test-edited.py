#!/usr/bin/env python3
"""Check suite-green-and-no-test-edited. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    return _lib.green_problems(ev.out())


if __name__ == "__main__":
    _lib.run(check)
