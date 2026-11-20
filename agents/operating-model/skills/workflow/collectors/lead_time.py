#!/usr/bin/env python3
"""Collector for the metric lead-time: Merge time minus the time of work-item-ready.

Reads: run-ledger.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("lead-time: collector not implemented (U13b)\n")
sys.exit(3)
