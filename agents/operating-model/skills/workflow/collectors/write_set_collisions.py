#!/usr/bin/env python3
"""Collector for the metric write-set-collisions: Pairs of units in the cut whose write-sets overlap: they share a file, or one lists a directory that contains a path of the other. Counted from the paths in the cut.

Reads: item.json, run-ledger.
No collector serves the source item.json, so the runtime records the reason
`no collector for item.json` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("write-set-collisions: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
