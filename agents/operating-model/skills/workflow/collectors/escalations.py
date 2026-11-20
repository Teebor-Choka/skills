#!/usr/bin/env python3
"""Collector for the metric escalations: Escalations taken in the run: each raise task that ran, to the lead or to the owner. A raise that did not run is not counted.

Reads: run-ledger.
Computed in-process by scripts/metric_collectors.py, the registry the org runtime calls.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("escalations: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
