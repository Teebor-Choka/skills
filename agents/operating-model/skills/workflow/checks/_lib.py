"""Shared helper for the check scripts (spec 6.1).

The runtime runs `checks/<name>.py <full task key>` with ORG_EVIDENCE, ORG_KEY and ORG_RUN set. The evidence
file is `{"run", "key", "steps": {<relative key>: {"exit", "stdout"}}}` and holds results of `by: code`
steps only. A check reads one step: the task itself when the task is a code step (`self_step`), else the code
step `<relative key>-evidence`. Its stdout is a JSON object that the check judges.

Exit 0 pass, 1 fail (reasons on stderr), 2 evidence missing, unreadable, or for another key or run.
"""
import json
import os
import sys


def die(code, msg):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def is_int(v):
    return type(v) is int and v >= 0


def is_str(v):
    return isinstance(v, str) and bool(v.strip())


def source_key(key, self_step):
    rel = key.split(">")[-1]
    return rel if self_step else rel + "-evidence"


def run(check, self_step=False, parse=True):
    """Load and bind the evidence, call check(data) -> list of problems, and exit."""
    if len(sys.argv) != 2:
        die(2, "usage: <check>.py <full task key>")
    key = sys.argv[1]
    path, org_key, org_run = (os.environ.get(n) for n in ("ORG_EVIDENCE", "ORG_KEY", "ORG_RUN"))
    if not (path and org_key and org_run):
        die(2, "ORG_EVIDENCE, ORG_KEY and ORG_RUN must be set")
    if key != org_key:
        die(2, f"argv key {key!r} differs from ORG_KEY {org_key!r}")
    try:
        with open(path, encoding="utf-8") as f:
            ev = json.load(f)
    except (OSError, ValueError) as e:
        die(2, f"cannot read evidence {path}: {e}")
    if not isinstance(ev, dict):
        die(2, "evidence must be a JSON object")
    if ev.get("key") != org_key:
        die(2, f"evidence key {ev.get('key')!r} differs from ORG_KEY {org_key!r}")
    if ev.get("run") != org_run:
        die(2, f"evidence run {ev.get('run')!r} differs from ORG_RUN {org_run!r}")
    steps = ev.get("steps")
    src = source_key(key, self_step)
    if not isinstance(steps, dict) or not isinstance(steps.get(src), dict):
        die(2, f"evidence has no result for the code step {src!r}")
    step = steps[src]
    if type(step.get("exit")) is not int or not isinstance(step.get("stdout"), str):
        die(2, f"step {src!r} must hold an integer exit and a string stdout")
    if step["exit"] != 0:
        die(1, f"evidence step {src!r} ended with exit {step['exit']}")
    data = {}
    if parse:
        try:
            data = json.loads(step["stdout"])
        except ValueError as e:
            die(2, f"stdout of step {src!r} is not JSON: {e}")
        if not isinstance(data, dict):
            die(2, f"stdout of step {src!r} must be a JSON object")
    try:
        problems = check(data)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        problems = [f"evidence has the wrong shape: {e!r}"]
    for p in problems:
        sys.stderr.write(p + "\n")
    sys.exit(1 if problems else 0)


def assertion_failures(data, need_expected=False):
    """Problems unless every recorded run failed on an assertion, and there is at least one run."""
    runs = data["runs"]
    if not isinstance(runs, list) or not runs:
        return ["no test run recorded"]
    problems = []
    for r in runs:
        if not (isinstance(r, dict) and is_str(r.get("test")) and is_str(r.get("outcome"))):
            return ["each run needs a test id and an outcome"]
        if r["outcome"] != "assertion":
            problems.append(f"{r['test']}: red run ended with '{r['outcome']}', not an assertion failure")
    if need_expected:
        expected = data["expected_tests"]
        if not (isinstance(expected, list) and expected and all(is_str(t) for t in expected)):
            return ["expected_tests must be a non-empty list of test ids"]
        seen = {r["test"] for r in runs}
        problems += [f"expected test {t} is absent from the run" for t in expected if t not in seen]
    return problems


def green_problems(data):
    suite = data["suite"]
    if not (isinstance(suite, dict) and is_int(suite.get("passed")) and is_int(suite.get("failed"))):
        return ["suite needs integer counts passed and failed"]
    edited = data["tests_edited"]
    if not (isinstance(edited, list) and all(isinstance(p, str) for p in edited)):
        return ["tests_edited must be a list of paths"]
    problems = []
    if suite["failed"] != 0:
        problems.append(f"{suite['failed']} test(s) fail")
    if suite["passed"] <= 0:
        problems.append("no test passed; an empty suite is not green")
    problems += [f"test file edited: {p}" for p in edited]
    return problems
