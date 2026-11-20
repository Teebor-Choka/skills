#!/usr/bin/env python3
"""Collector for the metric run-duration (metrics.runtime.json).

Reads: run-ledger. Computed in-process by scripts/metric_collectors.py, the registry the org runtime calls at run
end and at a turn boundary. This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("run-duration: computed in-process by scripts/metric_collectors.py\n")
sys.exit(3)
