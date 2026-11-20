#!/usr/bin/env python3
"""Collector for the metric proposals-accepted: Improver proposals that the owner accepted, divided by all proposals made.

Reads: proposal-records.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("proposals-accepted: collector not implemented (U13b)\n")
sys.exit(3)
