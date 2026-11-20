#!/usr/bin/env python3
"""Collector for the metric red-for-wrong-reason: Red runs in which the new test failed on a compile error, an import error or a timeout instead of an assertion.

Reads: test-runner-output.
Not implemented. The ledger and the collector calling convention come with U13b; until then this
script fails loudly so a metric is never recorded as zero by accident.
"""
import sys

sys.stderr.write("red-for-wrong-reason: collector not implemented (U13b)\n")
sys.exit(3)
