#!/usr/bin/env python3
"""Check checks-green-and-gate-approved. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(data):
    head, ci, gate = data["head"], data["ci"], data["gate"]
    if not (_lib.is_str(head) and isinstance(ci, dict) and isinstance(gate, dict)):
        return ["head, ci and gate are required"]
    problems = []
    if ci.get("state") != "success":
        problems.append(f"checks are {ci.get('state')!r}, not success")
    if ci.get("head") != head:
        problems.append("the checks ran on another head")
    if gate.get("decision") != "approve":
        problems.append(f"merge-gate decision is {gate.get('decision')!r}, not approve")
    if gate.get("signature_verified") is not True:
        problems.append("the gate decision signature is not verified")
    if gate.get("signer_role") != "owner":
        problems.append("the gate decision was not signed by the owner")
    if gate.get("head") != head:
        problems.append("the gate decision is for another head")
    return problems


if __name__ == "__main__":
    _lib.run(check, self_step=True, parse=True)
