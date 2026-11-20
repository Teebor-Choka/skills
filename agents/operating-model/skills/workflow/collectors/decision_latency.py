#!/usr/bin/env python3
"""Collector for the metric decision-latency: Time from the gate opening to the signed decision.

Reads: run-ledger.
Computed in-process by scripts/metric_collectors.py, the registry the org runtime calls.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("decision-latency: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
