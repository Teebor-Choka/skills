#!/usr/bin/env python3
"""Collector for the metric decision-latency: Time from the gate opening to the signed decision.

Reads: run-ledger.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("decision-latency: collector not implemented (U13b)\n")
sys.exit(3)
