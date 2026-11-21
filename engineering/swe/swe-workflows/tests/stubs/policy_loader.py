#!/usr/bin/env python3
"""Test double for the `policy` skill's loader.

policy-gate.sh calls `policy_loader.py <repo> --get KEY` and policy-context.sh calls it with
`--json` (FAKE_JSON is the resolved policy; FAKE_FAIL=1 simulates a malformed policy). The real
loader resolves the layered
.agents/policy. Here each test sets the resolved value directly via FAKE_<KEY> env (e.g.
FAKE_MODE=team), so the gate's block/warn decision can be exercised without the policy skill
installed. Unknown keys resolve to empty, matching the loader's "silent ⇒ caller default".
"""
import os
import sys

argv = sys.argv
if os.environ.get("FAKE_FAIL"):
    sys.exit(1)
if "--json" in argv:
    sys.stdout.write(os.environ.get("FAKE_JSON", "{}"))
if "--get" in argv:
    key = argv[argv.index("--get") + 1]
    sys.stdout.write(os.environ.get("FAKE_" + key.upper(), ""))
sys.exit(0)
