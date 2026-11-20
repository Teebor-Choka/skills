"""Acceptance tests for the shipped org root: sw-development, tdd-unit and improve, with the real metric
catalog and manifest (spec sections 6, 8, 9; brief U3).

Tests that read YAML need PyYAML and skip without it; the missing-package test always runs.
Run with: uv run --with pytest --with pyyaml --with jsonschema python -m pytest <this file> -q
"""
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_catalog as vc  # noqa: E402
import validate_manifest as vm  # noqa: E402
import validate_org as vo  # noqa: E402

WORKFLOWS = ["sw-development", "tdd-unit", "improve", "bug", "improvement-scan"]
APPENDIX_A = [
    "escalations", "spec-rework", "acceptance-coverage", "red-for-wrong-reason", "acceptance-rounds",
    "defects-found-in-review", "defects-escaped", "lead-time", "decision-latency", "write-set-collisions",
    "review-rounds", "report-complete", "proposals-accepted", "tests-per-unit", "diff-lines", "green-rounds",
]
HAS_YAML = importlib.util.find_spec("yaml") is not None
HAS_SCHEMA = HAS_YAML and importlib.util.find_spec("jsonschema") is not None
needs_yaml = pytest.mark.skipif(not HAS_YAML, reason="optional: uv run --with pyyaml")
needs_schema = pytest.mark.skipif(not HAS_SCHEMA, reason="optional: uv run --with pyyaml --with jsonschema")


def load(rel):
    return vc.load_document(str(ROOT / rel))


def workflow(name):
    return load(f"workflows/{name}.yaml")


def leaves(tasks, prefix=""):
    """Yield (path, body) for every task that is not a plain container of tasks."""
    for item in tasks:
        (name, body), = item.items()
        path = prefix + name
        if isinstance(body, dict) and isinstance(body.get("do"), list):
            yield from leaves(body["do"], path + "/")
        elif isinstance(body, dict) and isinstance(body.get("for"), dict) and "do" in body:
            yield from leaves(body["do"], path + "/")
        else:
            yield path, body


def all_leaves(name):
    return list(leaves(workflow(name)["do"]))


def refs():
    """Every brief, rubric, check and schema endpoint named by the three workflows."""
    out = {"brief": set(), "rubric": set(), "check": set(), "schema": set()}
    for name in WORKFLOWS:
        doc = workflow(name)
        for section in ("input", "output"):
            res = (doc.get(section) or {}).get("schema", {}).get("resource")
            if res:
                out["schema"].add(res["endpoint"])
        for path, body in leaves(doc["do"]):
            res = (body.get("output") or {}).get("schema", {}).get("resource")
            if res:
                out["schema"].add(res["endpoint"])
            org = (body.get("metadata") or {}).get("org") or {}
            if "brief" in org:
                out["brief"].add(org["brief"])
            for item in org.get("acceptance", []):
                if "check" in item:
                    out["check"].add(item["check"])
                if "rubric" in item:
                    out["rubric"].add(item["rubric"])
    return out


def run_cli(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)


# ---------------------------------------------------------------- 1. validators accept the real files


@needs_yaml
def test_metric_catalog_validates_and_holds_the_sixteen_metrics():
    cp = run_cli("validate_catalog.py", "--root", str(ROOT), str(ROOT / "metrics.json"))
    assert cp.returncode == 0, cp.stderr
    assert sorted(load("metrics.json")) == sorted(APPENDIX_A)


@needs_yaml
def test_manifest_validates():
    cp = run_cli("validate_manifest.py", "--root", str(ROOT), "--catalog", str(ROOT / "metrics.json"),
                 str(ROOT / "manifest.json"))
    assert cp.returncode == 0, cp.stderr


@needs_yaml
@pytest.mark.parametrize("name", WORKFLOWS)
def test_workflow_passes_validate_org(name):
    cp = run_cli("validate_org.py", "--catalog", str(ROOT / "metrics.json"), "--manifest",
                 str(ROOT / "manifest.json"), str(ROOT / "workflows" / f"{name}.yaml"))
    assert cp.returncode == 0, cp.stderr


@needs_schema
@pytest.mark.parametrize("name", WORKFLOWS)
def test_workflow_passes_the_ows_schema(name):
    cp = run_cli("check_flow_schema.py", str(ROOT / "workflows" / f"{name}.yaml"))
    assert cp.returncode == 0, cp.stdout + cp.stderr


@needs_yaml
def test_every_catalog_metric_is_used_by_a_node():
    used = set()
    for name in WORKFLOWS:
        for _, body in all_leaves(name):
            used.update(body["metadata"]["org"].get("metrics", []))
    assert used == set(APPENDIX_A)


@needs_yaml
def test_manifest_floors_match_the_floor_nodes():
    manifest = load("manifest.json")
    for name in WORKFLOWS:
        floors = [p for p, b in all_leaves(name) if b.get("metadata", {}).get("org", {}).get("floor") is True]
        assert sorted(manifest["workflows"][name]["floors"]) == sorted(p.rsplit("/", 1)[-1] for p in floors)
    assert sorted(manifest["workflows"]["sw-development"]["floors"]) == ["merge-gate", "review", "spec"]


# ---------------------------------------------------------------- 2. every reference resolves


@needs_yaml
def test_references_resolve_to_files():
    r = refs()
    assert len(r["brief"]) == 14 and len(r["rubric"]) == 9 and len(r["schema"]) == 2
    missing = [p for p in sorted(r["brief"] | r["rubric"] | r["schema"]) if not (ROOT / p).is_file()]
    missing += [f"checks/{c}.py" for c in sorted(r["check"]) if not (ROOT / "checks" / f"{c}.py").is_file()]
    assert missing == []
    assert all(p.startswith("briefs/sw/") for p in r["brief"])
    assert all(p.startswith("criteria/sw/") for p in r["rubric"])
    assert all(p.startswith("schemas/org/") for p in r["schema"])


@needs_yaml
def test_schemas_are_json_schemas_for_item_and_units():
    for name in ("item", "units"):
        doc = json.loads((ROOT / "schemas" / "org" / f"{name}.json").read_text())
        assert doc["type"] == "object" and doc["required"]
    units = json.loads((ROOT / "schemas" / "org" / "units.json").read_text())
    assert "units" in units["required"]


# ---------------------------------------------------------------- 3. every check runs on a fixture of each

ITEM = {
    "title": "Rate limit",
    "criteria": [{"id": "C1", "text": "A sixth request in one minute gets 429."},
                 {"id": "C2", "text": "The limit resets after one minute."}],
    "valid_inputs": "Any authenticated request.",
    "expected_outputs": "429 with Retry-After on the sixth request.",
    "failure_definition": "Store down: fail open and alert.",
    "performance": "100 requests per second, 5 ms budget.",
    "dependencies": "The store returns within 50 ms or the call counts as failed.",
    "out_of_scope": "Per-user quotas.",
    "ai_gap": "A build could pass every test and count requests per process, not per user.",
}
RUN, KEY = "r1", "some/key"
GREEN = {"suite": {"passed": 12, "failed": 0}, "tests_edited": []}
RUNS = {"runs": [{"test": "a", "outcome": "assertion"}, {"test": "b", "outcome": "assertion"}]}
REPORT_OK = "\n".join(f"## {h}\ntext" for h in
                      ["Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified"])
UNITS = {
    "units": [
        {"id": "u1", "goal": "g", "write_set": ["src/a.py"], "criteria": ["C1"], "depends_on": []},
        {"id": "u2", "goal": "g", "write_set": ["src/b.py"], "criteria": ["C2"], "depends_on": ["u1"]},
    ],
    "item_criteria_ids": ["C1", "C2"],
    "acceptance_test_paths": ["tests/test_acceptance.py"],
}
HEAD = {"head": "abc123", "ci": {"state": "success", "head": "abc123"},
        "gate": {"decision": "approve", "signature_verified": True, "signer_role": "owner", "head": "abc123"}}
CHANGE_DIRS = ("workflows", "briefs", "criteria", "schemas/org", "checks", "collectors", "bin")
CHANGE_FILES = ("manifest.json", "metrics.json")


def org_root_map():
    out = {}
    for d in CHANGE_DIRS:
        for p in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else []:
            if p.is_file() and "__pycache__" not in p.parts:
                out[p.relative_to(ROOT).as_posix()] = p.read_text()
    for f in CHANGE_FILES:
        if (ROOT / f).is_file():
            out[f] = (ROOT / f).read_text()
    return out


def proposal(edit_path="briefs/sw/red.md"):
    base = org_root_map()
    new = dict(base)
    new[edit_path] = base.get(edit_path, "") + "\nOne more rule.\n"
    return {"id": "p1", "base": base, "new": new}


GOOD = {
    "spec-check": {"item": ITEM},
    "spec-coverage": {"item": ITEM, "spec_criteria_ids": ["C1", "C2"],
                      "tests": [{"id": "a", "criteria": ["C1"]}, {"id": "b", "criteria": ["C2"]}]},
    "every-acceptance-test-fails-on-an-assertion": {**RUNS, "expected_tests": ["a", "b"]},
    "red-evidence": RUNS,
    "new-test-fails-on-an-assertion-not-a-compile-error": RUNS,
    "green-evidence": GREEN,
    "suite-green-and-no-test-edited": GREEN,
    "suite-still-green-and-no-test-edited": GREEN,
    "write-sets-are-disjoint": UNITS,
    "unit-verdict-is-pass": {},  # passes on the call step's own exit 0; nothing else is read
    "acceptance-suite-green": {**GREEN, "expected_count": 12},
    "checks-green-and-gate-approved": HEAD,
    "report-has-every-required-section": {"report": REPORT_OK},
    "every-proposal-is-within-its-rung": {"proposals": []},  # filled in below, needs the repo files
    "feasibility-holds": {"feasible": True, "failed": [], "reasons": ["every interface has an owner"]},
    "deploy-verified": {"verified": True, "exit": 0},
    "failing-test-committed": {"runs": [{"test": "test_bug.py::test_bug", "outcome": "assertion"}], "committed": True,
                               "files": ["test_bug.py"], "uncommitted": [], "base": "b1", "head": "h1"},
    "event-names-its-subject": {"run": "r1", "subject": "lessons and metrics of the run"},
}
if (ROOT / "checks").is_dir():
    GOOD["every-proposal-is-within-its-rung"] = {"proposals": [proposal()]}


def mut(ev, path, value=None, delete=False):
    ev = copy.deepcopy(ev)
    cur = ev
    for p in path[:-1]:
        cur = cur[p]
    if delete:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return ev


def unit_edit(i, field, value):
    return lambda e: mut(e, ["units", i, field], value)


BAD = {
    "spec-check": [
        ("empty criteria", lambda e: mut(e, ["item", "criteria"], [])),
        ("bad id", lambda e: mut(e, ["item", "criteria"], [{"id": "x y", "text": "t"}])),
        ("single criterion without id", lambda e: mut(e, ["item", "criteria"], [{"text": "t"}])),
        ("empty id", lambda e: mut(e, ["item", "criteria", 0, "id"], "")),
        ("n/a text", lambda e: mut(e, ["item", "criteria", 0, "text"], "n/a")),
        ("text not a string", lambda e: mut(e, ["item", "criteria", 0, "text"], 5)),
        ("duplicate id", lambda e: mut(e, ["item", "criteria", 1, "id"], "C1")),
        ("blank ai_gap", lambda e: mut(e, ["item", "ai_gap"], "  ")),
        ("blank category", lambda e: mut(e, ["item", "failure_definition"], "n/a")),
    ],
    "spec-coverage": [
        ("uncovered criterion", lambda e: mut(e, ["tests"], [{"id": "a", "criteria": ["C1"]}])),
        ("unknown criterion id", lambda e: mut(e, ["tests", 0, "criteria"], ["C1", "C9"])),
        ("criteria as a string", lambda e: mut(e, ["tests", 0, "criteria"], "C1")),
        ("item differs from the spec output", lambda e: mut(e, ["spec_criteria_ids"], ["C1", "C3"])),
    ],
    "every-acceptance-test-fails-on-an-assertion": [
        ("a test fails by compile error", lambda e: mut(e, ["runs", 1, "outcome"], "compile-error")),
        ("a test passes", lambda e: mut(e, ["runs", 1, "outcome"], "pass")),
        ("expected test absent", lambda e: mut(e, ["expected_tests"], ["a", "b", "c"])),
        ("no expected tests", lambda e: mut(e, ["expected_tests"], [])),
    ],
    "red-evidence": [
        ("no runs", lambda e: mut(e, ["runs"], [])),
        ("test passes", lambda e: mut(e, ["runs", 0, "outcome"], "pass")),
        ("timeout", lambda e: mut(e, ["runs", 0, "outcome"], "timeout")),
    ],
    "new-test-fails-on-an-assertion-not-a-compile-error": [
        ("import error", lambda e: mut(e, ["runs", 0, "outcome"], "import-error")),
    ],
    "green-evidence": [
        ("a test fails", lambda e: mut(e, ["suite", "failed"], 1)),
        ("empty suite", lambda e: mut(e, ["suite", "passed"], 0)),
        ("bool count", lambda e: mut(e, ["suite", "passed"], True)),
        ("float count", lambda e: mut(e, ["suite", "passed"], 12.0)),
        ("negative count", lambda e: mut(e, ["suite", "failed"], -1)),
        ("tests_edited missing", lambda e: mut(e, ["tests_edited"], delete=True)),
        ("tests_edited not a list", lambda e: mut(e, ["tests_edited"], "none")),
        ("a test edited", lambda e: mut(e, ["tests_edited"], ["tests/test_a.py"])),
    ],
    "suite-green-and-no-test-edited": [("a test edited", lambda e: mut(e, ["tests_edited"], ["t.py"]))],
    "suite-still-green-and-no-test-edited": [("a test edited", lambda e: mut(e, ["tests_edited"], ["t.py"]))],
    "acceptance-suite-green": [
        ("suite shrank", lambda e: mut(e, ["suite", "passed"], 10)),
        ("a test fails", lambda e: mut(e, ["suite", "failed"], 1)),
        ("expected_count not an int", lambda e: mut(e, ["expected_count"], 12.0)),
    ],
    "write-sets-are-disjoint": [
        ("identical files", unit_edit(1, "write_set", ["src/a.py"])),
        ("dir and file", unit_edit(0, "write_set", ["src"])),
        ("dir with slash and file", unit_edit(0, "write_set", ["src/"])),
        ("dotted path", unit_edit(1, "write_set", ["src/../src/a.py"])),
        ("parent segment", unit_edit(1, "write_set", ["../x.py"])),
        ("absolute path", unit_edit(1, "write_set", ["/etc/x"])),
        ("glob", unit_edit(1, "write_set", ["src/*.py"])),
        ("empty path", unit_edit(1, "write_set", [""])),
        ("empty write-set", unit_edit(1, "write_set", [])),
        ("covers checks", unit_edit(1, "write_set", ["checks/spec-check.py"])),
        ("covers criteria", unit_edit(1, "write_set", ["criteria/"])),
        ("covers manifest", unit_edit(1, "write_set", ["manifest.json"])),
        ("covers the acceptance tests", unit_edit(1, "write_set", ["tests/test_acceptance.py"])),
        ("duplicate unit id", unit_edit(1, "id", "u1")),
        ("no units", lambda e: mut(e, ["units"], [])),
        ("unknown dependency", unit_edit(1, "depends_on", ["u9"])),
        ("cyclic dependency", lambda e: mut(unit_edit(0, "depends_on", ["u2"])(e), ["units", 0, "depends_on"], ["u2"])),
        ("unknown criterion", unit_edit(1, "criteria", ["C9"])),
    ],
    "checks-green-and-gate-approved": [
        ("checks red", lambda e: mut(e, ["ci", "state"], "failure")),
        ("gate rejected", lambda e: mut(e, ["gate", "decision"], "reject")),
        ("signature not verified", lambda e: mut(e, ["gate", "signature_verified"], False)),
        ("signer not owner", lambda e: mut(e, ["gate", "signer_role"], "lead")),
        ("gate on another head", lambda e: mut(e, ["gate", "head"], "def456")),
        ("ci on another head", lambda e: mut(e, ["ci", "head"], "def456")),
    ],
    "report-has-every-required-section": [
        ("missing section", lambda e: mut(e, ["report"], REPORT_OK.replace("## Metrics\ntext\n", ""))),
        ("empty section", lambda e: mut(e, ["report"], REPORT_OK.replace("## Metrics\ntext", "## Metrics\n"))),
        ("heading only inside a fence", lambda e: mut(
            e, ["report"], REPORT_OK.replace("## Metrics\ntext", "```\n## Metrics\ntext\n```"))),
    ],
    "feasibility-holds": [
        ("not feasible", lambda e: mut(mut(e, ["feasible"], False), ["failed"], ["modularity"])),
        ("feasible but a dimension failed", lambda e: mut(e, ["failed"], ["testability"])),
        ("no reasons", lambda e: mut(e, ["reasons"], [])),
    ],
    "deploy-verified": [
        ("verification failed", lambda e: mut(mut(e, ["verified"], False), ["exit"], 3)),
        ("did not run", lambda e: mut(e, ["exit"], None)),
        ("verified with a failing exit", lambda e: mut(e, ["exit"], 1)),
    ],
    "failing-test-committed": [
        ("not committed", lambda e: mut(mut(e, ["committed"], False), ["uncommitted"], ["test_bug.py"])),
        ("committed but dirty", lambda e: mut(e, ["uncommitted"], ["test_bug.py"])),
        ("the test passes", lambda e: mut(e, ["runs", 0, "outcome"], "pass")),
        ("the test errors", lambda e: mut(e, ["runs", 0, "outcome"], "import-error")),
        ("nothing committed since the base", lambda e: mut(e, ["head"], "b1")),
    ],
    "event-names-its-subject": [
        ("no subject", lambda e: mut(e, ["subject"], " ")),
        ("no run", lambda e: mut(e, ["run"], "")),
    ],
    "every-proposal-is-within-its-rung": [
        ("no proposals", lambda e: mut(e, ["proposals"], [])),
        ("touches a floor", lambda e: mut(e, ["proposals"], [proposal("criteria/sw/spec.md")])),
        ("changes nothing", lambda e: mut(e, ["proposals"], [{**proposal(), "new": proposal()["base"]}])),
        ("cannot be classified", lambda e: mut(e, ["proposals", 0, "base"], "not a map")),
        ("self-declared rung is ignored", lambda e: mut(
            e, ["proposals"], [{**proposal("criteria/sw/spec.md"), "rung": "free"}])),
    ],
}
CHANGE_OK = (SCRIPTS / "check_change.py").is_file() and HAS_YAML
CHANGE_WHY = "needs scripts/check_change.py (U15) and PyYAML"
needs_change = pytest.mark.skipif(not CHANGE_OK, reason=CHANGE_WHY)
RUNG = "every-proposal-is-within-its-rung"


TASK = {  # check name -> (full key of a task that names it, whether that task is itself a by: code step)
    "spec-check": ("spec", False),
    "spec-coverage": ("acceptance-tests", False),
    "every-acceptance-test-fails-on-an-assertion": ("acceptance-red", True),
    "red-evidence": ("cycle/red", False),
    "new-test-fails-on-an-assertion-not-a-compile-error": ("cycle/red-evidence", True),
    "green-evidence": ("cycle/green", False),
    "suite-green-and-no-test-edited": ("cycle/green-evidence", True),
    "suite-still-green-and-no-test-edited": ("cycle/refactor", False),
    "write-sets-are-disjoint": ("cut", False),
    "unit-verdict-is-pass": ("build/units/tdd#0", True),
    "acceptance-suite-green": ("build/acceptance-run", True),
    "checks-green-and-gate-approved": ("merge", True),
    "report-has-every-required-section": ("report", True),
    "every-proposal-is-within-its-rung": ("propose", False),
    "feasibility-holds": ("spec-cycle/design-cycle/feasibility", True),
    "deploy-verified": ("verify", True),
    "failing-test-committed": ("reproduce-evidence", True),
    "event-names-its-subject": ("reflect", True),
}
SOURCE_RULE = lambda key, is_self: key if is_self else key + "-evidence"  # noqa: E731


def wrap(name, data, key=None, run=RUN, exit_code=0, stdout=None):
    """The evidence file of spec 6.1: only code-step results, under their relative keys."""
    task, is_self = TASK[name]
    key = key or task
    out = json.dumps(data) if stdout is None else stdout
    return {"run": run, "key": key, "steps": {SOURCE_RULE(task, is_self): {"exit": exit_code, "stdout": out}}}


def run_check(name, data, key=None, run=RUN, env=None, argv_key=None, checks_dir=None, raw=None):
    task = TASK[name][0]
    key = key or task
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "evidence.json"
        ev.write_text(raw if raw is not None else json.dumps(wrap(name, data, key=key, run=run)))
        e = {k: v for k, v in os.environ.items() if not k.startswith("ORG_")}
        e.update({"ORG_EVIDENCE": str(ev), "ORG_KEY": task, "ORG_RUN": RUN, "ORG_ALLOWED_RUNGS": "free,ordinary"})
        e.update(env or {})
        e = {k: v for k, v in e.items() if v is not None}
        script = Path(checks_dir or ROOT / "checks") / f"{name}.py"
        return subprocess.run([sys.executable, str(script), argv_key or task],
                              capture_output=True, text=True, env=e)


def needs(name):
    return needs_change if name == RUNG else (lambda f: f)


@pytest.mark.parametrize("name", sorted(GOOD))
def test_check_passes_on_good_evidence(name):
    if name == RUNG and not CHANGE_OK:
        pytest.skip(CHANGE_WHY)
    cp = run_check(name, GOOD[name])
    assert cp.returncode == 0, cp.stderr


CASE_IDS = [(n, i) for n in sorted(BAD) for i in range(len(BAD[n]))]


@pytest.mark.parametrize("name,i", CASE_IDS, ids=[f"{n}:{BAD[n][i][0]}" for n, i in CASE_IDS])
def test_check_fails_on_each_bad_case_and_says_why(name, i):
    if name == RUNG and not CHANGE_OK:
        pytest.skip(CHANGE_WHY)
    label, fn = BAD[name][i]
    cp = run_check(name, {k: v for k, v in fn(copy.deepcopy(GOOD[name])).items()})
    assert cp.returncode == 1, f"{label}: {cp.stdout}{cp.stderr}"
    assert cp.stderr.strip()


EMPTY_OK = {"tests_edited", "failed", "uncommitted"}
GENERIC = [n for n in sorted(GOOD) if n != RUNG]


@pytest.mark.parametrize("name", GENERIC)
def test_every_field_is_required_typed_and_non_empty(name):
    good = GOOD[name]
    for field, value in good.items():
        wrong = 42 if isinstance(value, list) else ["x"]
        for label, ev in (("missing", mut(good, [field], delete=True)), ("wrong type", mut(good, [field], wrong))):
            cp = run_check(name, ev)
            assert cp.returncode == 1, f"{name}.{field} {label}: exit {cp.returncode}"
        if isinstance(value, (list, str, dict)) and field not in EMPTY_OK:
            cp = run_check(name, mut(good, [field], type(value)()))
            assert cp.returncode == 1, f"{name}.{field} empty: exit {cp.returncode}"


def test_rung_check_needs_every_field():
    if not CHANGE_OK:
        pytest.skip(CHANGE_WHY)
    for ev in ({}, {"proposals": "x"}, {"proposals": [{"id": "p1"}]}):
        assert run_check(RUNG, ev).returncode == 1


# ---- the evidence contract (spec 6.1, _lib): key and run binding, exit codes


@pytest.mark.parametrize("name", sorted(GOOD))
def test_evidence_for_another_task_exits_two(name):
    cp = run_check(name, GOOD[name], key="other/key")
    assert cp.returncode == 2 and "key" in cp.stderr


@pytest.mark.parametrize("name", sorted(GOOD))
def test_stale_evidence_from_another_run_exits_two(name):
    cp = run_check(name, GOOD[name], run="r0")
    assert cp.returncode == 2 and "run" in cp.stderr


@pytest.mark.parametrize("name", sorted(GOOD))
def test_evidence_without_key_run_or_the_source_step_exits_two(name):
    for drop in ("key", "run", "steps"):
        ev = wrap(name, GOOD[name])
        del ev[drop]
        assert run_check(name, None, raw=json.dumps(ev)).returncode == 2, drop
    ev = wrap(name, GOOD[name])
    ev["steps"] = {"unrelated": {"exit": 0, "stdout": "{}"}}
    assert run_check(name, None, raw=json.dumps(ev)).returncode == 2


@pytest.mark.parametrize("name", sorted(GOOD))
def test_a_failed_evidence_step_fails_the_check(name):
    cp = run_check(name, None, raw=json.dumps(wrap(name, GOOD[name], exit_code=1)))
    assert cp.returncode == 1 and "exit" in cp.stderr


@pytest.mark.parametrize("name", [n for n in sorted(GOOD) if n != "unit-verdict-is-pass"])
def test_unparseable_evidence_stdout_exits_two(name):
    assert run_check(name, None, raw=json.dumps(wrap(name, None, stdout="not json"))).returncode == 2
    assert run_check(name, None, raw=json.dumps(wrap(name, None, stdout="[1]"))).returncode == 2


@pytest.mark.parametrize("name", sorted(GOOD))
def test_a_model_step_result_is_not_evidence(name):
    # a by: model task's own step key must not be read as its evidence; only <task>-evidence is
    task, is_self = TASK[name]
    if is_self:
        pytest.skip("a code step is its own evidence")
    ev = wrap(name, GOOD[name])
    ev["steps"] = {task: ev["steps"].popitem()[1]}
    assert run_check(name, None, raw=json.dumps(ev)).returncode == 2


def test_lib_exit_two_on_missing_or_unreadable_evidence(tmp_path):
    script = ROOT / "checks" / "unit-verdict-is-pass.py"
    task = "build/units/tdd#0"
    base = {k: v for k, v in os.environ.items() if not k.startswith("ORG_")}

    def go(env, argv=(task,)):
        return subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True,
                              env={**base, **env}).returncode

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    arr = tmp_path / "arr.json"
    arr.write_text("[]")
    ok = {"ORG_RUN": RUN, "ORG_KEY": task}
    assert go({}) == 2
    assert go({**ok, "ORG_EVIDENCE": str(tmp_path / "none.json")}) == 2
    assert go({**ok, "ORG_EVIDENCE": str(bad)}) == 2
    assert go({**ok, "ORG_EVIDENCE": str(arr)}) == 2
    assert go({"ORG_KEY": task, "ORG_EVIDENCE": str(arr)}) == 2  # ORG_RUN missing
    assert go({"ORG_RUN": RUN, "ORG_EVIDENCE": str(arr)}) == 2  # ORG_KEY missing
    assert go({**ok, "ORG_EVIDENCE": str(arr)}, argv=()) == 2  # no key argument
    assert go({**ok, "ORG_EVIDENCE": str(arr)}, argv=("other",)) == 2  # argv differs from ORG_KEY


def test_lib_has_no_unused_test_outcomes():
    assert "TEST_OUTCOMES" not in (ROOT / "checks" / "_lib.py").read_text()


@needs_change
def test_rung_check_takes_allowed_rungs_from_the_runtime_only():
    ev = GOOD[RUNG]
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": None}).returncode == 1
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": ""}).returncode == 1
    assert run_check(RUNG, {**ev, "allowed_rungs": ["free", "frozen"]},
                     env={"ORG_ALLOWED_RUNGS": None}).returncode == 1
    floor = {"proposals": [proposal("criteria/sw/spec.md")]}
    assert run_check(RUNG, floor, env={"ORG_ALLOWED_RUNGS": "free,ordinary"}).returncode == 1
    assert run_check(RUNG, floor, env={"ORG_ALLOWED_RUNGS": "free,ordinary,frozen"}).returncode == 0
    # a loop bound outside a floor is ordinary (O1, K17), so the free rung alone refuses it
    bound = proposal("workflows/sw-development.yaml")
    bound["new"]["workflows/sw-development.yaml"] = bound["base"]["workflows/sw-development.yaml"].replace(
        "{ each: build-round, in: [1, 2, 3] }", "{ each: build-round, in: [1, 2, 3, 4] }")
    assert bound["new"] != bound["base"]
    assert run_check(RUNG, {"proposals": [bound]}, env={"ORG_ALLOWED_RUNGS": "free"}).returncode == 1
    assert run_check(RUNG, {"proposals": [bound]}, env={"ORG_ALLOWED_RUNGS": "free,ordinary"}).returncode == 0


def test_rung_check_fails_closed_without_check_change(tmp_path):
    shutil.copytree(ROOT / "checks", tmp_path / "checks")  # no ../scripts beside the copy
    cp = run_check(RUNG, {"proposals": [{"id": "p", "base": {}, "new": {"a": "b"}}]},
                   checks_dir=tmp_path / "checks")
    assert cp.returncode == 1 and "check_change" in cp.stderr


@pytest.mark.parametrize("name", sorted(GOOD))
def test_every_pass_fixture_matches_the_documented_shape(name):
    readme = (ROOT / "checks" / "README.md").read_text()
    row = re.search(rf"(?m)^\| `{re.escape(name)}`\s*\|.*$", readme)
    assert row, f"{name} is not in the shape table of checks/README.md"
    documented = set(re.findall(r"`([a-z_]+)`", row.group(0).split("|")[-2]))
    assert documented == set(GOOD[name])


def test_readme_states_the_contract():
    text = (ROOT / "checks" / "README.md").read_text()
    for needle in ("ORG_EVIDENCE", "ORG_KEY", "ORG_RUN", "ORG_ALLOWED_RUNGS", "frozen", "never from agent output",
                   "trust boundary", "Summary", "Not verified", "defaults taken by the orchestrator"):
        assert needle.lower() in text.lower(), needle


@needs_yaml
def test_missing_check_script_for_a_named_check_fails():
    assert sorted(refs()["check"]) == sorted(GOOD)


# ---------------------------------------------------------------- bin and collectors are loud stubs


@needs_yaml
def test_non_agent_commands_are_executable_files_in_bin():
    cmds = set()
    for name in WORKFLOWS:
        for _, body in all_leaves(name):
            shell = (body.get("run") or {}).get("shell")
            if shell and shell["command"] != "agent-run":
                cmds.add(shell["command"])
    assert cmds == {"tdd-evidence", "merge-change"}
    for c in cmds:
        f = ROOT / "bin" / c
        assert f.is_file() and os.access(f, os.X_OK), c
        assert "not implemented" not in f.read_text()  # U14 built both (test_cycle.py runs them)


@pytest.mark.parametrize("metric", APPENDIX_A)
def test_collector_stub_exits_three_with_the_stub_message(metric):
    path = ROOT / "collectors" / (metric.replace("-", "_") + ".py")
    cp = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    assert cp.returncode == 3 and "collector not implemented (U13b)" in cp.stderr


# ---------------------------------------------------------------- 4. rubrics state numbered rules and a fail report


@needs_yaml
def test_rubrics_have_numbered_rules_and_a_fail_report():
    rubrics = sorted(refs()["rubric"])
    assert rubrics
    for rel in rubrics:
        text = (ROOT / rel).read_text()
        rules = re.findall(r"(?m)^\d+\. \S", text)
        assert len(rules) >= 3, f"{rel}: needs at least three numbered pass rules"
        m = re.search(r"(?m)^## On a fail\s*\n(.+)", text)
        assert m, f"{rel}: no '## On a fail' section"
        assert "report" in m.group(1).lower(), f"{rel}: the fail section does not say what the judge reports"


def test_briefs_are_not_empty():
    briefs = sorted((ROOT / "briefs" / "sw").glob("*.md"))
    assert len(briefs) == 14
    assert all(len(b.read_text().split()) > 40 for b in briefs)


# ---------------------------------------------------------------- 5. adversarial: losing acceptance or metrics fails


@needs_yaml
@pytest.mark.parametrize("name", WORKFLOWS)
def test_every_leaf_has_acceptance_and_metrics(name):
    for path, body in all_leaves(name):
        org = body["metadata"]["org"]
        if "to" in org:  # escalation (raise)
            continue
        assert org.get("acceptance"), f"{name}:{path} has no acceptance list"
        assert org.get("metrics"), f"{name}:{path} has no metrics"


def _validate(doc):
    catalog = load("metrics.json")
    manifest = load("manifest.json")
    return vo.validate_org(doc, catalog, manifest)


@needs_yaml
@pytest.mark.parametrize("name", WORKFLOWS)
@pytest.mark.parametrize("key", ["acceptance", "metrics"])
def test_dropping_a_list_from_any_node_is_refused(name, key):
    base = workflow(name)
    assert _validate(base) == []
    victims = [p for p, b in all_leaves(name) if "to" not in b["metadata"]["org"]]
    assert victims
    for victim in victims:
        doc = copy.deepcopy(base)
        parts = victim.split("/")
        tasks = doc["do"]
        for part in parts:
            for item in tasks:
                if part in item:
                    body = item[part]
                    tasks = body.get("do", [])
                    break
        del body["metadata"]["org"][key]
        assert _validate(doc), f"dropping {key} from {name}:{victim} was not refused"


@needs_yaml
def test_removing_a_floor_from_the_workflow_is_refused():
    doc = workflow("sw-development")
    for item in doc["do"]:
        if "merge-gate" in item:
            del item["merge-gate"]["metadata"]["org"]["floor"]
    assert any("merge-gate" in e for e in _validate(doc))


# ---------------------------------------------------------------- the missing-package path always runs


def test_yaml_without_pyyaml_exits_two_with_the_hint(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("do: []\n")
    code = ("import sys; sys.modules['yaml'] = None; sys.path.insert(0, %r); import validate_catalog as v; "
            "sys.exit(v.main(['--root', '.', %r]))" % (str(SCRIPTS), str(f)))
    cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert cp.returncode == 2
    assert "PyYAML" in cp.stderr


# ---------------------------------------------------------------- review 1: rubrics, briefs, catalog, snapshot


def rubric_text(name):
    return (ROOT / "criteria" / "sw" / f"{name}.md").read_text()


def test_review_floor_rubric_requires_an_approving_verdict():
    text = rubric_text("review")
    assert re.search(r"(?m)^\d+\. The reviewer's verdict is approve and no upheld defect is open", text)
    assert "reject verdict fails the item" in text.split("## On a fail")[1]


def test_unit_review_rubric_requires_a_passing_verdict():
    text = rubric_text("unit-review")
    assert re.search(r"(?m)^\d+\. The reviewer's verdict is pass and no upheld defect is open", text)
    assert "fail verdict fails the item" in text.split("## On a fail")[1]


@needs_yaml
def test_every_rubric_rule_names_its_evidence_and_a_missing_input_fails():
    for rel in sorted(refs()["rubric"]):
        text = (ROOT / rel).read_text()
        rules = re.findall(r"(?m)^\d+\. (.+)$", text)
        assert all("Judged against:" in r for r in rules), f"{rel}: a rule names no evidence"
        assert "unreadable or missing input is a fail" in text.split("## On a fail")[1], rel


def test_acceptance_tests_rubric_splits_rule_four_and_scopes_edge_cases():
    text = rubric_text("acceptance-tests")
    assert "where meaningful" in text.lower()
    assert len(re.findall(r"(?m)^\d+\. ", text)) >= 5


def test_spec_item_has_an_ai_gap_field():
    schema = json.loads((ROOT / "schemas" / "org" / "item.json").read_text())
    assert "ai_gap" in schema["required"] and schema["properties"]["ai_gap"]["minLength"] == 1
    assert "ai_gap" in (ROOT / "briefs" / "sw" / "spec.md").read_text()


@pytest.mark.parametrize("brief", ["red", "acceptance-tests", "cut"])
def test_briefs_state_the_write_set(brief):
    assert "write-set" in (ROOT / "briefs" / "sw" / f"{brief}.md").read_text().lower()


def test_cut_brief_says_units_are_built_one_after_another():
    text = (ROOT / "briefs" / "sw" / "cut.md").read_text()
    assert "one after another" in text and "not in parallel" in text


def test_improve_brief_follows_the_rung_table_and_never_asks_for_a_rung():
    text = (ROOT / "briefs" / "sw" / "improve.md").read_text()
    assert "state the rung" not in text.lower() and "rung each" not in text.lower()
    for needle in ("ordinary", "frozen", "protected", "floor task", "do not state a rung"):
        assert needle in text.lower(), needle


@needs_yaml
def test_improve_step_has_an_inline_timeout():
    (name, body), = workflow("improve")["do"][0].items()
    assert body["timeout"]["after"]


@needs_yaml
def test_catalog_definitions_match_their_units():
    m = load("metrics.json")
    assert "per change" in m["defects-escaped"]["unit"] and "30 days" in m["defects-escaped"]["formula"]
    assert "outcome 'pass'" in m["red-for-wrong-reason"]["formula"] or "passed" in m["red-for-wrong-reason"]["formula"]
    assert "zero" in m["proposals-accepted"]["formula"] and "free" in m["proposals-accepted"]["formula"]
    assert "never green" in m["acceptance-rounds"]["formula"]
    assert "upheld" in m["defects-found-in-review"]["formula"] and "per change" in m["defects-found-in-review"]["unit"]
    assert "paths" in m["write-set-collisions"]["formula"]
    for section in ("Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified"):
        assert section in m["report-complete"]["formula"]
    for name in ("review-rounds", "green-rounds", "escalations"):
        assert len(m[name]["formula"].split()) > 12, name


@needs_yaml
@pytest.mark.parametrize("name", ["sw-development", "tdd-unit"])
def test_shipped_workflow_equals_the_normalised_example_snapshot(name):
    snap = json.loads((HERE / "fixtures" / "examples" / "snapshot.json").read_text())
    assert workflow(name) == snap[name]
