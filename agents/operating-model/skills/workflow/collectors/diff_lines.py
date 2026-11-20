#!/usr/bin/env python3
"""Collector for the metric diff-lines: Lines added plus lines removed in a unit.

Reads: git-diff.
No collector serves the source git-diff, so the runtime records the reason
`no collector for git-diff` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("diff-lines: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
