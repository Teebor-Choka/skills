#!/usr/bin/env python3
"""Check checks-green-and-gate-approved. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

def check(ev):
    head = ev.change()["head"]
    ci = ev.out()["ci"]
    gate = ev.decision("merge-gate")
    if not isinstance(ci, dict):
        return ["ci must be a map"]
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
    if gate.get("run") != ev.run:
        problems.append("the gate decision is for another run")
    return problems


if __name__ == "__main__":
    _lib.run(check)
