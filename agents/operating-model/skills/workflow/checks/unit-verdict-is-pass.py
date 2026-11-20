#!/usr/bin/env python3
"""Check unit-verdict-is-pass. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    return [] if ev["verdict"] == "pass" else [f"unit verdict is '{ev['verdict']}'"]


if __name__ == "__main__":
    _lib.run(check)
