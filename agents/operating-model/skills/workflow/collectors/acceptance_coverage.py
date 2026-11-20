#!/usr/bin/env python3
"""Collector for the metric acceptance-coverage: Criteria in the approved item that have at least one acceptance test, divided by all criteria in the item.

Reads: item.json, test-ids.
No collector serves the source item.json, so the runtime records the reason
`no collector for item.json` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("acceptance-coverage: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
