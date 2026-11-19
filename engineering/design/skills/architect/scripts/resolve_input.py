#!/usr/bin/env python3
"""Resolve the inputs the architect must not guess: invocation arg, then policy, then ask or halt.

Order per field: (1) the invocation arg, (2) a `.agents/policy` key, (3) a question, only when an
interactive channel exists. Non-interactive (the default) with a field still missing: HALT with a
structured `needs-input` result that names each missing field and the exact arg or policy key that
supplies it. A rung, scope or target is never defaulted. Stated defaults: output location (policy
`work.tracker`, else GitHub issues) and box cap (5), both written into the report.

Result (one JSON object): {"status": "ready"|"needs-input"|"ask", "resolved": {field: {value, source}},
"missing": [{field, arg, policy_key, why}]}. Exit codes: 0 ready, 3 needs-input, 4 ask.
Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import sys

LADDER = ["interfaces", "modules", "components", "functions"]
DEFAULT_CAP = 5
DEFAULT_OUTPUT = "github issues"

# field -> (invocation arg, policy key)
FIELDS = {
    "depth": ("--depth", "architect.depth"),
    "scope": ("--scope", "architect.scope"),
    "target": ("--target", "architect.improve-target"),
    "output": ("--output", "work.tracker"),
    "cap": ("--cap", "architect.box-cap"),
}
NEEDS = {"design": ["depth", "scope"], "improve": ["target", "output", "cap"]}
DEFAULTS = {"output": DEFAULT_OUTPUT, "cap": str(DEFAULT_CAP)}
UNSET = {"", "none", "null", "-"}


def find_loader(explicit=None):
    """Locate the policy skill's loader: explicit path, env, PATH, then a repo checkout above here."""
    for cand in (explicit, os.environ.get("AGENTS_POLICY_LOADER"), shutil.which("policy_loader.py")):
        if cand and os.path.exists(cand):
            return cand
    here = os.path.dirname(os.path.abspath(__file__))
    while here != os.path.dirname(here):
        cand = os.path.join(here, "agents", "operating-model", "skills", "policy", "policy_loader.py")
        if os.path.exists(cand):
            return cand
        here = os.path.dirname(here)
    return None


def policy_get(loader, repo, key):
    if not loader:
        return None
    try:
        out = subprocess.run([sys.executable, loader, repo, "--get", key], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    val = out.stdout.strip()
    return val if out.returncode == 0 and val.lower() not in UNSET else None


def _invalid(field, value):
    if field == "depth":
        return None if value.lower() in LADDER else f"'{value}' is not one of {'|'.join(LADDER)}"
    if field == "cap":
        return None if value.isascii() and value.isdigit() and int(value) > 0 else f"'{value}' is not a positive number"
    return None


def resolve(mode, args, loader, repo, interactive=False):
    """args: {field: value or None}. Returns the result dict described in the module docstring."""
    resolved, missing = {}, []
    for field in NEEDS[mode]:
        arg, key = FIELDS[field]
        value, source = args.get(field), f"arg {arg}"
        if value is None:
            value, source = policy_get(loader, repo, key), f"policy {key}"
        if value is None and field in DEFAULTS:
            value, source = DEFAULTS[field], "default"
        if value is None:
            missing.append({"field": field, "arg": arg, "policy_key": key, "why": "not given"})
            continue
        bad = _invalid(field, value)
        if bad:
            missing.append({"field": field, "arg": arg, "policy_key": key, "why": bad})
            continue
        resolved[field] = {"value": value.lower() if field == "depth" else value, "source": source}
    status = "ready" if not missing else ("ask" if interactive else "needs-input")
    return {"status": status, "mode": mode, "resolved": resolved, "missing": missing}


EXIT = {"ready": 0, "needs-input": 3, "ask": 4}


def emit(result):
    print(json.dumps(result))
    return EXIT[result["status"]]
