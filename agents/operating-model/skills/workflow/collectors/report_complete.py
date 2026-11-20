#!/usr/bin/env python3
"""Collector for the metric report-complete: Required sections with a non-empty body in the final report, divided by all six: Summary, Acceptance, Tests, Defects, Metrics, Not verified.

Reads: report.md.
No collector serves the source report.md, so the runtime records the reason
`no collector for report.md` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("report-complete: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
