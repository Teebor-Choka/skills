#!/usr/bin/env python3
"""Collector for the metric acceptance-rounds: Build rounds until the acceptance suite is green. When the suite is never green within the round bound, the value is the bound and the run raises acceptance-not-met.

Reads: run-ledger.
Computed in-process by scripts/metric_collectors.py, the registry the org runtime calls.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("acceptance-rounds: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
