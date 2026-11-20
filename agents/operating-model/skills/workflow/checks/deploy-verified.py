#!/usr/bin/env python3
"""Check deploy-verified. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    data = ev.out()
    if not _lib.is_int(data["exit"]):
        return [f"deploy verification did not run to an exit status: {data.get('reason', 'no reason given')}"]
    if data["verified"] is not True:
        return [f"deploy verification failed with exit {data['exit']}"]
    if data["exit"] != 0:
        return ["verified is true but the exit status is not 0"]
    return []

if __name__ == "__main__":
    _lib.run(check)
