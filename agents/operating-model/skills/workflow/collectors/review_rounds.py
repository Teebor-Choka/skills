#!/usr/bin/env python3
"""Collector for the metric review-rounds: Review rounds until the verdict approves the change.

Reads: verdict-records.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("review-rounds: collector not implemented (U13b)\n")
sys.exit(3)
