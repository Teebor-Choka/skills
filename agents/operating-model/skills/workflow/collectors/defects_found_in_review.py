#!/usr/bin/env python3
"""Collector for the metric defects-found-in-review: Findings of the whole-change review that the owner's verdict upheld. A finding is upheld when the verdict is reject for it or the owner confirms it; one per distinct file, line and criterion.

Reads: verdict-records.
No collector serves the source verdict-records, so the runtime records the reason
`no collector for verdict-records` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("defects-found-in-review: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
