#!/usr/bin/env python3
"""Collector for the metric defects-escaped: Defects filed against a merged change within 30 days of its merge, counted per change.

Reads: tracker.
No collector serves the source tracker, so the runtime records the reason
`no collector for tracker` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("defects-escaped: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
