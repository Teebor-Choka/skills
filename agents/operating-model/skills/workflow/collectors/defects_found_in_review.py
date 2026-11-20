#!/usr/bin/env python3
"""Collector for the metric defects-found-in-review: Review findings that the verdict upheld.

Reads: verdict-records.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("defects-found-in-review: collector not implemented (U13b)\n")
sys.exit(3)
