#!/usr/bin/env python3
"""Collector for the metric green-rounds: Green rounds until the suite passes with no test file touched.

Reads: run-ledger.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("green-rounds: collector not implemented (U13b)\n")
sys.exit(3)
