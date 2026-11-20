#!/usr/bin/env python3
"""Collector for the metric report-complete: Required sections present in the final report, divided by all required sections.

Reads: report.md.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("report-complete: collector not implemented (U13b)\n")
sys.exit(3)
