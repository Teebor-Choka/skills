#!/usr/bin/env python3
"""Collector for the metric proposals-accepted: Improver proposals that were applied, divided by all proposals made. A proposal on the free rung counts as accepted when it was applied; an ordinary one when the reviewer approved it; a protected one when the owner signed it. With zero proposals made the value is not recorded.

Reads: proposal-records.
No collector serves the source proposal-records, so the runtime records the reason
`no collector for proposal-records` for this metric, never a value.
This file exists because the catalog names a collector path; run on its own it exits 3.
"""
import sys

sys.stderr.write("proposals-accepted: not a standalone collector, see scripts/metric_collectors.py\n")
sys.exit(3)
