"""Shared helper for the check scripts (spec 6.1, evidence file of update 6).

The runtime runs `checks/<name>.py <full task key>` with ORG_EVIDENCE, ORG_KEY and ORG_RUN set (and
ORG_ALLOWED_RUNGS for the rung check). The evidence file is
`{"run", "key", "output", "steps", "outputs", "decisions", "change", "input"}`; see README.md for what each check
reads. `input` is the workflow execution's input (P55); tdd-unit's is `{"unit": {..., "write_set", "new_symbols"}}`.

Exit 0 pass, 1 fail (reasons on stderr), 2 evidence missing, unreadable, or for another key or run.
"""
import json
import os
import re
import sys

TEST_FILE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")  # the same rule as bin/tdd-evidence


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


def _find(table, rel, what):
    """Entry for a relative key. A task inside a loop has a path (`spec-cycle/spec`); a check names the task
    by its own name (`spec`), so fall back to the one key that ends in it. Two matches are an error."""
    if rel in table:
        return table[rel]
    hits = [k for k in table if k.rsplit("/", 1)[-1] == rel]
    if len(hits) > 1:
        die(2, f"evidence has several {what} entries for '{rel}': {', '.join(sorted(hits))}")
    if not hits:
        die(2, f"evidence has no {what} entry for '{rel}'")
    return table[hits[0]]


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
        return _json(_find(self._part("outputs"), rel, "outputs"), f"outputs['{rel}']")

    def fact(self, rel):
        """The result of an earlier by: code step."""
        return _json(_find(self._part("steps"), rel, "steps"), f"steps['{rel}']")

    def decision(self, rel):
        found = _find(self._part("decisions"), rel, "decisions")
        if not isinstance(found, dict):
            die(2, f"decision '{rel}' must be a map")
        return found

    def unit(self):
        """The `unit` of the workflow input (P55), or {} when there is none."""
        inp = self.raw.get("input")
        unit = inp.get("unit") if isinstance(inp, dict) else None
        return unit if isinstance(unit, dict) else {}

    def write_set(self):
        ws = self.unit().get("write_set")
        if not (isinstance(ws, list) and ws and all(is_str(w) for w in ws)):
            die(2, "evidence input has no unit write_set (a non-empty list of paths)")
        return ws

    def new_symbols(self):
        """True when the unit declares the names it adds (P59); a malformed declaration is a fail."""
        names = self.unit().get("new_symbols")
        if names is None:
            return False
        if not (isinstance(names, list) and names and all(is_str(n) for n in names)):
            die(1, "unit new_symbols must be a non-empty list of names")
        return True

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


def in_write_set(path, write_set):
    return any(path == w.rstrip("/") or path.startswith(w.rstrip("/") + "/") for w in write_set)


def assertion_failures(runs, expected=None, missing_symbol_ok=False):
    """Problems unless every recorded run failed on an assertion, and there is at least one run.
    With `missing_symbol_ok` (the unit declares `new_symbols`, P59) an `import-error` or `error` run counts too:
    the test calls a name that does not exist yet. A compile error or a timeout never counts."""
    allowed = ("assertion", "import-error", "error") if missing_symbol_ok else ("assertion",)
    if not isinstance(runs, list) or not runs:
        return ["no test run recorded"]
    problems = []
    for r in runs:
        if not (isinstance(r, dict) and is_str(r.get("test")) and is_str(r.get("outcome"))):
            return ["each run needs a test id and an outcome"]
        if r["outcome"] not in allowed:
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
