#!/usr/bin/env python3
"""Collector for the metric defects-escaped: Defects filed against a merged change within 30 days of the merge.

Reads: tracker.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("defects-escaped: collector not implemented (U13b)\n")
sys.exit(3)
