#!/usr/bin/env python3
"""Check report-has-every-required-section. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import re

SECTIONS = ("Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified")


def bodies(text):
    """Map heading -> body text, ignoring headings and lines inside code fences."""
    out, cur, fenced = {}, None, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            if cur is not None:
                out[cur] += line + "\n"
            continue
        m = None if fenced else re.match(r"#{1,3} (.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, "")
        elif cur is not None:
            out[cur] += line + "\n"
    return out


def check(data):
    text = data["report"]
    if not _lib.is_str(text):
        return ["report must be a non-empty string"]
    found = bodies(text)
    return [f"report lacks the section '{s}'" if s not in found else f"section '{s}' is empty"
            for s in SECTIONS if not found.get(s, "").strip()]


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
