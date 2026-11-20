#!/usr/bin/env python3
"""Check new-test-fails-on-an-assertion-not-a-compile-error. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    return _lib.assertion_failures(ev.out()["runs"])


if __name__ == "__main__":
    _lib.run(check)
