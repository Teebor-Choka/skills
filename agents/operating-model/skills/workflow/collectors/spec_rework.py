#!/usr/bin/env python3
"""Collector for the metric spec-rework: Times the spec was reopened after spec-check had passed it.

Reads: run-ledger, tracker-edit-history.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("spec-rework: collector not implemented (U13b)\n")
sys.exit(3)
