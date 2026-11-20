#!/usr/bin/env python3
"""Collector for the metric tests-per-unit: Tests added or changed in a unit.

Reads: test-ids, git-diff.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("tests-per-unit: collector not implemented (U13b)\n")
sys.exit(3)
