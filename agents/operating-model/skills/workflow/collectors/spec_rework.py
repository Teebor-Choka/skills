#!/usr/bin/env python3
"""Collector for the metric spec-rework: Times the spec was reopened after spec-check had passed it.

Reads: run-ledger, tracker-edit-history.
No collector serves the source tracker-edit-history, so the runtime records the reason
`no collector for tracker-edit-history` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("spec-rework: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
