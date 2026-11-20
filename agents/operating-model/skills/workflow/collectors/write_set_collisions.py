#!/usr/bin/env python3
"""Collector for the metric write-set-collisions: Pairs of units in the cut whose write-sets share at least one file.

Reads: item.json, run-ledger.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("write-set-collisions: collector not implemented (U13b)\n")
sys.exit(3)
