#!/usr/bin/env python3
"""Check report-has-every-required-section. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import re

SECTIONS = ("Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified")
EMPTY = {"n/a", "na", "none", "tbd", "todo", "-"}


def bodies(text):
    """Map heading -> body text, ignoring headings and lines inside ``` or ~~~ code fences."""
    out, cur, fence = {}, None, None
    for line in text.splitlines():
        m = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if m:
            if fence is None:
                fence = m.group(1)[0]
            elif m.group(1)[0] == fence:
                fence = None
            if cur is not None:
                out[cur] += line + "\n"
            continue
        h = None if fence else re.match(r"#{1,3} (.+?)\s*$", line)
        if h:
            cur = h.group(1)
            out.setdefault(cur, "")
        elif cur is not None:
            out[cur] += line + "\n"
    return out


def check(ev):
    text = ev.out()["report"]
    if not _lib.is_str(text):
        return ["report must be a non-empty string"]
    found = bodies(text)
    problems = []
    for s in SECTIONS:
        if s not in found:
            problems.append(f"report lacks the section '{s}'")
        elif not found[s].strip() or found[s].strip().lower().rstrip(".") in EMPTY:
            problems.append(f"section '{s}' is empty or a placeholder")
    return problems


if __name__ == "__main__":
    _lib.run(check)
