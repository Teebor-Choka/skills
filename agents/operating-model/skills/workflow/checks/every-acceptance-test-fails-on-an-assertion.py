#!/usr/bin/env python3
"""Check every-acceptance-test-fails-on-an-assertion. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(data):
    return _lib.assertion_failures(data, need_expected=True)


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
