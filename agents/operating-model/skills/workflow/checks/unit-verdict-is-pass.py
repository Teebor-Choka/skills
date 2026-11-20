#!/usr/bin/env python3
"""Check unit-verdict-is-pass. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(_ev):
    """The call entry is exit 0 when the called workflow ended in success; _lib already refused any other exit."""
    return []


if __name__ == "__main__":
    _lib.run(check, parse_output=False)
