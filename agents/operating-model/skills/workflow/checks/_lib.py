"""Shared helper for the check scripts (spec 6.1, evidence file of update 6).

The runtime runs `checks/<name>.py <full task key>` with ORG_EVIDENCE, ORG_KEY and ORG_RUN set (and
ORG_ALLOWED_RUNGS for the rung check). The evidence file is
`{"run", "key", "output", "steps", "outputs", "decisions", "change"}`; see README.md for what each check reads.

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


def _entry(e, label):
    if not (isinstance(e, dict) and type(e.get("exit")) is int and isinstance(e.get("stdout"), str)):
        die(2, f"{label} must be an entry with an integer exit and a string stdout")
    return e


def _json(e, label):
    try:
        data = json.loads(_entry(e, label)["stdout"])
    except ValueError as err:
        die(2, f"stdout of {label} is not JSON: {err}")
    if not isinstance(data, dict):
        die(2, f"stdout of {label} must be a JSON object")
    return data


class Evidence:
    def __init__(self, raw):
        self.raw = raw
        self.run = raw["run"]
        self.key = raw["key"]
        self.output = _entry(raw.get("output"), "output")

    def _part(self, name):
        part = self.raw.get(name)
        if not isinstance(part, dict):
            die(2, f"evidence has no map '{name}'")
        return part

    def out(self):
        """The checked task's own output, parsed. A claim when the task is a model step, a fact when code."""
        return _json(self.output, "output")

    def claim(self, rel):
        """The output of an earlier task: a claim to validate, never trusted."""
        outputs = self._part("outputs")
        if rel not in outputs:
            die(2, f"evidence has no outputs entry for '{rel}'")
        return _json(outputs[rel], f"outputs['{rel}']")

    def fact(self, rel):
        """The result of an earlier by: code step."""
        steps = self._part("steps")
        if rel not in steps:
            die(2, f"evidence has no steps entry for '{rel}'")
        return _json(steps[rel], f"steps['{rel}']")

    def decision(self, rel):
        decisions = self._part("decisions")
        if not isinstance(decisions.get(rel), dict):
            die(2, f"evidence has no decision for '{rel}'")
        return decisions[rel]

    def change(self):
        c = self._part("change")
        if not (is_str(c.get("head")) and is_str(c.get("worktree"))):
            die(2, "change needs a head and a worktree")
        return c


def run(check, parse_output=True):
    """Load and bind the evidence, call check(Evidence) -> list of problems, and exit."""
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
            raw = json.load(f)
    except (OSError, ValueError) as e:
        die(2, f"cannot read evidence {path}: {e}")
    if not isinstance(raw, dict):
        die(2, "evidence must be a JSON object")
    if raw.get("key") != org_key:
        die(2, f"evidence key {raw.get('key')!r} differs from ORG_KEY {org_key!r}")
    if raw.get("run") != org_run:
        die(2, f"evidence run {raw.get('run')!r} differs from ORG_RUN {org_run!r}")
    ev = Evidence(raw)
    if ev.output["exit"] != 0:
        die(1, f"the checked task ended with exit {ev.output['exit']}")
    if parse_output:
        ev.out()  # exit 2 now when the output is not a JSON object
    try:
        problems = check(ev)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:
        problems = [f"evidence has the wrong shape: {e!r}"]
    for p in problems:
        sys.stderr.write(p + "\n")
    sys.exit(1 if problems else 0)


def assertion_failures(runs, expected=None):
    """Problems unless every recorded run failed on an assertion, and there is at least one run."""
    if not isinstance(runs, list) or not runs:
        return ["no test run recorded"]
    problems = []
    for r in runs:
        if not (isinstance(r, dict) and is_str(r.get("test")) and is_str(r.get("outcome"))):
            return ["each run needs a test id and an outcome"]
        if r["outcome"] != "assertion":
            problems.append(f"{r['test']}: red run ended with '{r['outcome']}', not an assertion failure")
    if expected is not None:
        if not (isinstance(expected, list) and expected and all(is_str(t) for t in expected)):
            return ["no claimed acceptance tests to compare the run with"]
        seen = {r["test"] for r in runs}
        problems += [f"claimed test {t} is absent from the run" for t in expected if t not in seen]
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
