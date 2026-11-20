#!/usr/bin/env python3
"""Check event-names-its-subject. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    data = ev.out()
    return [f"the event data needs a non-empty {key}" for key in ("run", "subject") if not _lib.is_str(data.get(key))]

if __name__ == "__main__":
    _lib.run(check)
