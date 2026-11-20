#!/usr/bin/env python3
"""Collector for the metric green-rounds: Green attempts of one unit until the suite passes with no test file edited. Each failed green-evidence in a cycle round counts one.

Reads: run-ledger.
Computed in-process by scripts/metric_collectors.py, the registry the org runtime calls.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("green-rounds: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
