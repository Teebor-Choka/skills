#!/usr/bin/env python3
"""Check report-has-every-required-section. See _lib.py for the calling convention."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import re

SECTIONS = ("Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified")


def check(ev):
    have = set(re.findall(r"(?m)^#{1,3} (.+?)\s*$", ev["report"]))
    return [f"report lacks the section '{s}'" for s in SECTIONS if s not in have]


if __name__ == "__main__":
    _lib.run(check)
