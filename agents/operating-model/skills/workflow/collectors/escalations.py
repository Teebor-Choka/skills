#!/usr/bin/env python3
"""Collector for the metric escalations: Escalation connections taken in the run: a raise to the lead or to the owner.

Reads: run-ledger.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("escalations: collector not implemented (U13b)\n")
sys.exit(3)
