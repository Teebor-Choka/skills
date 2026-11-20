#!/usr/bin/env python3
"""Check unit-verdict-is-pass. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(_data):
    """The call step's own exit 0 means the called workflow ended without raising; _lib checks the exit."""
    return []


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=False)
