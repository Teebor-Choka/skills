#!/usr/bin/env python3
"""Collector for the metric red-for-wrong-reason: Red runs in which the new test did not fail on an assertion: it ended with a compile error, an import error or a timeout, or it passed.

Reads: test-runner-output.
No collector serves the source test-runner-output, so the runtime records the reason
`no collector for test-runner-output` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("red-for-wrong-reason: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
