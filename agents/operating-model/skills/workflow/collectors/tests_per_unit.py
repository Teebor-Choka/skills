#!/usr/bin/env python3
"""Collector for the metric tests-per-unit: Tests added or changed in a unit.

Reads: test-ids, git-diff.
No collector serves the source test-ids, so the runtime records the reason
`no collector for test-ids` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("tests-per-unit: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
