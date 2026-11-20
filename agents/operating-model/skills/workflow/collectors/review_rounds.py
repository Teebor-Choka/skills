#!/usr/bin/env python3
"""Collector for the metric review-rounds: Number of review rounds on the change until the review verdict is approve. The review floor runs once per run, so a value above 1 counts earlier runs of the same item.

Reads: verdict-records.
No collector serves the source verdict-records, so the runtime records the reason
`no collector for verdict-records` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("review-rounds: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
