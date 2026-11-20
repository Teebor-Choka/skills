#!/usr/bin/env python3
"""Check every-proposal-is-within-its-rung. See README.md in this directory for the evidence it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import os
import sys

RUNGS = ("free", "ordinary", "protected", "frozen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))


def to_bytes(files, label):
    if not (isinstance(files, dict) and all(isinstance(k, str) and (v is None or isinstance(v, str))
                                            for k, v in files.items())):
        raise ValueError(f"{label} must map a path to a string or null")
    return {k: None if v is None else v.encode("utf-8") for k, v in files.items()}


def check(data):
    raw = os.environ.get("ORG_ALLOWED_RUNGS", "")
    allowed = {r for r in raw.split(",") if r}
    if not allowed or not allowed <= set(RUNGS):
        return ["ORG_ALLOWED_RUNGS must name the rungs the runtime allows (set by the runtime, never by evidence)"]
    proposals = data["proposals"]
    if not (isinstance(proposals, list) and proposals):
        return ["no proposals recorded"]
    try:
        from check_change import check_change
    except ImportError as e:
        return [f"cannot import check_change (scripts/check_change.py): {e}"]
    problems = []
    for p in proposals:
        pid = p.get("id", "?") if isinstance(p, dict) else "?"
        try:
            entries, refused = check_change(to_bytes(p["base"], "base"), to_bytes(p["new"], "new"), allowed)
        except Exception as e:  # a proposal that cannot be classified fails
            problems.append(f"proposal {pid} cannot be classified: {e!r}")
            continue
        if not entries:
            problems.append(f"proposal {pid} changes nothing")
        problems += [f"proposal {pid}: {path} is rung '{rung}' ({row}), allowed: {sorted(allowed)}"
                     for path, _task, row, rung in refused]
    return problems


if __name__ == "__main__":
    _lib.run(check, self_step=False, parse=True)
