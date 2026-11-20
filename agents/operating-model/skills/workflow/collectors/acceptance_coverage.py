#!/usr/bin/env python3
"""Collector for the metric acceptance-coverage: Criteria in the approved item that have at least one acceptance test, divided by all criteria in the item.

Reads: item.json, test-ids.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("acceptance-coverage: collector not implemented (U13b)\n")
sys.exit(3)
