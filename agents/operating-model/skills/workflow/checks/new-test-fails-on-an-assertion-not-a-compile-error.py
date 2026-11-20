#!/usr/bin/env python3
"""Check new-test-fails-on-an-assertion-not-a-compile-error. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

check = _lib.assertion_failures


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
