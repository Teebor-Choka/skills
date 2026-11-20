"""Shared helper for the check scripts.

A check is run as `checks/<name>.py <full task key>`. The runtime puts the path of a JSON evidence file
for that task in the environment variable ORG_EVIDENCE. Exit 0 is pass, 1 is fail (reasons on stderr),
2 is missing or unreadable evidence, which the runtime also treats as fail.
"""
import json
import os
import sys

TEST_OUTCOMES = ("assertion", "compile-error", "import-error", "timeout", "pass")


def run(check):
    """Load the evidence, call check(evidence) -> list of problems, and exit."""
    path = os.environ.get("ORG_EVIDENCE")
    if not path:
        sys.stderr.write("ORG_EVIDENCE is not set\n")
        sys.exit(2)
    try:
        with open(path, encoding="utf-8") as f:
            evidence = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write(f"cannot read evidence {path}: {e}\n")
        sys.exit(2)
    if not isinstance(evidence, dict):
        sys.stderr.write("evidence must be a JSON object\n")
        sys.exit(2)
    try:
        problems = check(evidence)
    except (KeyError, TypeError, AttributeError) as e:
        problems = [f"evidence has the wrong shape: {e!r}"]
    for p in problems:
        sys.stderr.write(p + "\n")
    sys.exit(1 if problems else 0)


def assertion_failures(evidence):
    """Problems unless every recorded run failed on an assertion, and there is at least one run."""
    runs = evidence["runs"]
    if not runs:
        return ["no test run recorded"]
    return [f"{r['test']}: red run ended with '{r['outcome']}', not an assertion failure"
            for r in runs if r["outcome"] != "assertion"]


def green_problems(evidence):
    suite = evidence["suite"]
    problems = []
    if suite["failed"] != 0:
        problems.append(f"{suite['failed']} test(s) fail")
    if suite["passed"] <= 0:
        problems.append("no test passed; an empty suite is not green")
    problems += [f"test file edited: {p}" for p in evidence.get("tests_edited", [])]
    return problems
