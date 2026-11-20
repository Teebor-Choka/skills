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
@pytest.mark.skipif("checks" not in vm.TOP_KEYS, reason="validate_manifest predates spec update 6 (U2 follow-up)")
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
    assert len(r["brief"]) == 15 and len(r["rubric"]) == 13 and len(r["schema"]) == 2
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


# ---------------------------------------------------------------- 3. every check runs on a fixture of each (spec 6.1)

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
RUN = "r1"
HEAD = "abc123"
RUNS = {"runs": [{"test": "a", "outcome": "assertion"}, {"test": "b", "outcome": "assertion"}]}
GREEN = {"suite": {"passed": 12, "failed": 0}, "tests_edited": []}
ACC_GREEN = {"suite": {"passed": 2, "failed": 0}, "tests_edited": []}
AT_OUT = {"tests": [{"id": "a", "criteria": ["C1"], "path": "tests/test_acceptance.py"},
                    {"id": "b", "criteria": ["C2"], "path": "tests/test_acceptance.py"}]}
REPORT_OK = "\n".join(f"## {h}\ntext" for h in
                      ["Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified"])
UNITS = {"units": [
    {"id": "u1", "goal": "g", "write_set": ["src/a.py"], "criteria": ["C1"], "depends_on": []},
    {"id": "u2", "goal": "g", "write_set": ["src/b.py"], "criteria": ["C2"], "depends_on": ["u1"]},
]}
# the tdd-unit workflow input (P55): the red fact compares `changed` with the unit's write_set (P57)
UNIT_INPUT = {"unit": {"id": "sum", "write_set": ["calc.py", "test_add.py"]}}
DECISION = {"decision": "approve", "signer_role": "owner", "signature_verified": True, "run": RUN,
            "task": "merge-gate", "head": HEAD}
# check name -> spec of its evidence: the task it sits on, the checked task's own output (`out`, JSON data, or
# `out_raw`, a string), and what it reads from `outputs` (claims), `steps` (code-step facts), `decisions`.
SPECS = {
    "spec-check": dict(task="spec", out=ITEM),
    "spec-coverage": dict(task="acceptance-tests", out=AT_OUT, outputs={"spec": ITEM}),
    "every-acceptance-test-fails-on-an-assertion": dict(task="acceptance-red", out=RUNS,
                                                        outputs={"acceptance-tests": AT_OUT}),
    "red-evidence": dict(task="cycle/red-evidence", out=dict(RUNS, changed=["test_add.py"]), input=UNIT_INPUT),
    "new-test-fails-on-an-assertion-not-a-compile-error": dict(task="cycle/red-evidence", out=RUNS, input=UNIT_INPUT),
    "green-evidence": dict(task="cycle/green-evidence", out=GREEN),
    "suite-green-and-no-test-edited": dict(task="cycle/green-evidence", out=GREEN),
    "suite-still-green-and-no-test-edited": dict(task="cycle/refactor-evidence", out=GREEN),
    "write-sets-are-disjoint": dict(task="cut", out=UNITS, outputs={"spec": ITEM, "acceptance-tests": AT_OUT}),
    "unit-verdict-is-pass": dict(task="build/units/tdd#0", out_raw=""),
    "acceptance-suite-green": dict(task="build/acceptance-run", out=ACC_GREEN, steps={"acceptance-red": RUNS}),
    "checks-green-and-gate-approved": dict(task="merge", out={"ci": {"state": "success", "head": HEAD}},
                                           decisions={"merge-gate": DECISION}),
    "report-has-every-required-section": dict(task="report", out={"report": REPORT_OK}),
    "feasibility-holds": dict(task="spec-cycle/design-cycle/feasibility",
                              out={"feasible": True, "failed": [], "reasons": ["every interface has an owner"]}),
    "deploy-verified": dict(task="verify", out={"verified": True, "exit": 0}),
    "failing-test-committed": dict(task="reproduce-evidence", out={
        "runs": [{"test": "test_bug.py::test_bug", "outcome": "assertion"}], "committed": True,
        "files": ["test_bug.py"], "uncommitted": [], "base": "b1", "head": "h1"}),
    "phase-acceptance-green": dict(task="spec-cycle/design-cycle/system-run", out={
        "suite": {"passed": 3, "failed": 0}, "tests_edited": [], "system_fault": "none", "expected_count": 3}),
    "event-names-its-subject": dict(task="reflect", out={"run": RUN, "subject": "lessons and metrics of the run"}),
}
RUNG = "every-proposal-is-within-its-rung"
ALL_CHECKS = sorted([*SPECS, RUNG])
FACT = {"every-acceptance-test-fails-on-an-assertion", "red-evidence",
        "new-test-fails-on-an-assertion-not-a-compile-error", "green-evidence", "suite-green-and-no-test-edited",
        "suite-still-green-and-no-test-edited", "acceptance-suite-green", "checks-green-and-gate-approved",
        "feasibility-holds", "deploy-verified", "failing-test-committed", "phase-acceptance-green"}


def entry(data):
    return {"exit": 0, "stdout": json.dumps(data)}


def build(spec, run=RUN, key=None, change=None):
    """The evidence file of spec 6.1, built from a spec dict."""
    out = {"exit": 0, "stdout": spec["out_raw"]} if "out_raw" in spec else entry(spec["out"])
    return {"input": spec.get("input", {}),
        "run": run, "key": key or spec["task"], "output": out,
        "steps": {k: entry(v) for k, v in spec.get("steps", {}).items()},
        "outputs": {k: entry(v) for k, v in spec.get("outputs", {}).items()},
        "decisions": spec.get("decisions", {}),
        "change": change or {"head": HEAD, "worktree": "/nonexistent"},
    }


def mut(spec, path, value=None, delete=False):
    spec = copy.deepcopy(spec)
    cur = spec
    for p in path[:-1]:
        cur = cur[p]
    if delete:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return spec


def unit_edit(i, field, value):
    return lambda s: mut(s, ["out", "units", i, field], value)


def with_tests(tests):
    return lambda s: mut(s, ["outputs", "acceptance-tests"], {"tests": tests})


def raw_out(text):
    return lambda s: mut(s, ["out"], {"report": text})


BAD = {
    "spec-check": [
        ("empty criteria", lambda s: mut(s, ["out", "criteria"], [])),
        ("bad id", lambda s: mut(s, ["out", "criteria"], [{"id": "x y", "text": "t"}])),
        ("single criterion without id", lambda s: mut(s, ["out", "criteria"], [{"text": "t"}])),
        ("empty id", lambda s: mut(s, ["out", "criteria", 0, "id"], "")),
        ("n/a text", lambda s: mut(s, ["out", "criteria", 0, "text"], "n/a")),
        ("text not a string", lambda s: mut(s, ["out", "criteria", 0, "text"], 5)),
        ("duplicate id", lambda s: mut(s, ["out", "criteria", 1, "id"], "C1")),
        ("blank ai_gap", lambda s: mut(s, ["out", "ai_gap"], "  ")),
        ("placeholder category", lambda s: mut(s, ["out", "failure_definition"], "n/a")),
    ],
    "spec-coverage": [
        ("uncovered criterion", lambda s: mut(s, ["out", "tests"], [AT_OUT["tests"][0]])),
        ("unknown criterion id", lambda s: mut(s, ["out", "tests", 0, "criteria"], ["C1", "C9"])),
        ("criteria as a string", lambda s: mut(s, ["out", "tests", 0, "criteria"], "C1")),
        ("no tests", lambda s: mut(s, ["out", "tests"], [])),
    ],
    "every-acceptance-test-fails-on-an-assertion": [
        ("compile error", lambda s: mut(s, ["out", "runs", 1, "outcome"], "compile-error")),
        ("a test passes", lambda s: mut(s, ["out", "runs", 1, "outcome"], "pass")),
        ("claimed test absent from the run", with_tests(AT_OUT["tests"] + [{"id": "c", "criteria": ["C1"], "path": "t"}])),
        ("no claimed tests", with_tests([])),
    ],
    "red-evidence": [
        ("no runs", lambda s: mut(s, ["out", "runs"], [])),
        ("test passes", lambda s: mut(s, ["out", "runs", 0, "outcome"], "pass")),
        ("timeout", lambda s: mut(s, ["out", "runs", 0, "outcome"], "timeout")),
        ("production file changed at red", lambda s: mut(s, ["out", "changed"], ["calc.py", "test_add.py"])),
        ("production file inside a write-set directory changed", lambda s: mut(
            mut(s, ["input", "unit", "write_set"], ["src/", "tests/test_add.py"]), ["out", "changed"], ["src/calc.py"])),
        ("import error without new_symbols", lambda s: mut(s, ["out", "runs", 0, "outcome"], "import-error")),
        ("compile error with new_symbols", lambda s: mut(
            mut(s, ["input", "unit", "new_symbols"], ["add"]), ["out", "runs", 0, "outcome"], "compile-error")),
    ],
    "new-test-fails-on-an-assertion-not-a-compile-error": [
        ("import error", lambda s: mut(s, ["out", "runs", 0, "outcome"], "import-error")),
    ],
    "green-evidence": [
        ("a test fails", lambda s: mut(s, ["out", "suite", "failed"], 1)),
        ("empty suite", lambda s: mut(s, ["out", "suite", "passed"], 0)),
        ("bool count", lambda s: mut(s, ["out", "suite", "passed"], True)),
        ("float count", lambda s: mut(s, ["out", "suite", "passed"], 12.0)),
        ("negative count", lambda s: mut(s, ["out", "suite", "failed"], -1)),
        ("tests_edited missing", lambda s: mut(s, ["out", "tests_edited"], delete=True)),
        ("tests_edited not a list", lambda s: mut(s, ["out", "tests_edited"], "none")),
        ("a test edited", lambda s: mut(s, ["out", "tests_edited"], ["tests/test_a.py"])),
    ],
    "suite-green-and-no-test-edited": [("a test edited", lambda s: mut(s, ["out", "tests_edited"], ["t.py"]))],
    "suite-still-green-and-no-test-edited": [("a test edited", lambda s: mut(s, ["out", "tests_edited"], ["t.py"]))],
    "acceptance-suite-green": [
        ("suite shrank against the red run", lambda s: mut(s, ["out", "suite", "passed"], 1)),
        ("a test fails", lambda s: mut(s, ["out", "suite", "failed"], 1)),
        ("a test edited", lambda s: mut(s, ["out", "tests_edited"], ["tests/test_acceptance.py"])),
        ("red run has no runs", lambda s: mut(s, ["steps", "acceptance-red"], {"runs": []})),
    ],
    "write-sets-are-disjoint": [
        ("identical files", unit_edit(1, "write_set", ["src/a.py"])),
        ("dir and file", unit_edit(0, "write_set", ["src"])),
        ("dir with slash and file", unit_edit(0, "write_set", ["src/"])),
        ("parent segment", unit_edit(1, "write_set", ["../x.py"])),
        ("dotted path", unit_edit(1, "write_set", ["src/../src/a.py"])),
        ("absolute path", unit_edit(1, "write_set", ["/etc/x"])),
        ("glob", unit_edit(1, "write_set", ["src/*.py"])),
        ("empty path", unit_edit(1, "write_set", [""])),
        ("empty write-set", unit_edit(1, "write_set", [])),
        ("covers checks", unit_edit(1, "write_set", ["checks/spec-check.py"])),
        ("covers checks in other case", unit_edit(1, "write_set", ["Checks/spec-check.py"])),
        ("covers criteria", unit_edit(1, "write_set", ["criteria/"])),
        ("covers manifest.json", unit_edit(1, "write_set", ["manifest.json"])),
        ("covers MANIFEST.JSON", unit_edit(1, "write_set", ["MANIFEST.JSON"])),
        ("covers manifest.yaml", unit_edit(1, "write_set", ["manifest.yaml"])),
        ("covers metrics.yaml", unit_edit(1, "write_set", ["Metrics.yaml"])),
        ("covers the acceptance tests", unit_edit(1, "write_set", ["tests/test_acceptance.py"])),
        ("covers the acceptance tests dir", unit_edit(1, "write_set", ["tests"])),
        ("acceptance test paths not a list", lambda s: mut(s, ["outputs", "acceptance-tests"], {"tests": "x"})),
        ("acceptance test paths missing", lambda s: mut(
            s, ["outputs", "acceptance-tests"], {"tests": [{"id": "a", "criteria": ["C1"]}]})),
        ("duplicate unit id", unit_edit(1, "id", "u1")),
        ("no units", lambda s: mut(s, ["out", "units"], [])),
        ("unknown dependency", unit_edit(1, "depends_on", ["u9"])),
        ("cyclic dependency", lambda s: mut(unit_edit(0, "depends_on", ["u2"])(s), ["out", "units", 1, "depends_on"], ["u1"])),
        ("unknown criterion", unit_edit(1, "criteria", ["C9"])),
    ],
    "checks-green-and-gate-approved": [
        ("checks red", lambda s: mut(s, ["out", "ci", "state"], "failure")),
        ("ci on another head", lambda s: mut(s, ["out", "ci", "head"], "def456")),
        ("gate rejected", lambda s: mut(s, ["decisions", "merge-gate", "decision"], "reject")),
        ("signature not verified", lambda s: mut(s, ["decisions", "merge-gate", "signature_verified"], False)),
        ("signer not owner", lambda s: mut(s, ["decisions", "merge-gate", "signer_role"], "lead")),
        ("gate for another head", lambda s: mut(s, ["decisions", "merge-gate", "head"], "def456")),
    ],
    "feasibility-holds": [
        ("not feasible", lambda s: mut(mut(s, ["out", "feasible"], False), ["out", "failed"], ["modularity"])),
        ("feasible but a dimension failed", lambda s: mut(s, ["out", "failed"], ["testability"])),
        ("no reasons", lambda s: mut(s, ["out", "reasons"], [])),
    ],
    "deploy-verified": [
        ("verification failed", lambda s: mut(mut(s, ["out", "verified"], False), ["out", "exit"], 3)),
        ("did not run", lambda s: mut(s, ["out", "exit"], None)),
        ("verified with a failing exit", lambda s: mut(s, ["out", "exit"], 1)),
    ],
    "failing-test-committed": [
        ("not committed", lambda s: mut(mut(s, ["out", "committed"], False), ["out", "uncommitted"], ["test_bug.py"])),
        ("committed but dirty", lambda s: mut(s, ["out", "uncommitted"], ["test_bug.py"])),
        ("the test passes", lambda s: mut(s, ["out", "runs", 0, "outcome"], "pass")),
        ("the test errors", lambda s: mut(s, ["out", "runs", 0, "outcome"], "import-error")),
        ("nothing committed since the base", lambda s: mut(s, ["out", "head"], "b1")),
    ],
    "phase-acceptance-green": [
        ("a declared test failed", lambda s: mut(mut(s, ["out", "system_fault"], "design"), ["out", "suite", "failed"], 1)),
        ("a fault with a green suite", lambda s: mut(s, ["out", "system_fault"], "spec")),
        ("both faults", lambda s: mut(s, ["out", "layer_fault"], "none")),
        ("suite shrank", lambda s: mut(s, ["out", "suite", "passed"], 2)),
        ("a test edited", lambda s: mut(s, ["out", "tests_edited"], ["tests/test_a.py"])),
        ("empty suite", lambda s: mut(mut(s, ["out", "suite", "passed"], 0), ["out", "expected_count"], 0)),
    ],
    "event-names-its-subject": [
        ("no subject", lambda s: mut(s, ["out", "subject"], " ")),
        ("no run", lambda s: mut(s, ["out", "run"], "")),
    ],
    "report-has-every-required-section": [
        ("missing section", raw_out(REPORT_OK.replace("## Metrics\ntext\n", ""))),
        ("empty section", raw_out(REPORT_OK.replace("## Metrics\ntext", "## Metrics\n"))),
        ("n/a body", raw_out(REPORT_OK.replace("## Metrics\ntext", "## Metrics\nn/a"))),
        ("heading only inside a ``` fence", raw_out(
            REPORT_OK.replace("## Metrics\ntext", "```\n## Metrics\ntext\n```"))),
        ("heading only inside a ~~~ fence", raw_out(
            REPORT_OK.replace("## Metrics\ntext", "~~~\n## Metrics\ntext\n~~~"))),
    ],
}
GOOD = {n: SPECS[n] for n in SPECS}


def run_check(name, evidence, env=None, argv_key=None, checks_dir=None, org_key=None):
    """Run a check on an evidence dict (or raw text). Default env is a well-formed runtime."""
    key = evidence.get("key") if isinstance(evidence, dict) else None
    task = SPECS[name]["task"] if name in SPECS else "propose"
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "evidence.json"
        ev.write_text(evidence if isinstance(evidence, str) else json.dumps(evidence))
        e = {k: v for k, v in os.environ.items() if not k.startswith("ORG_")}
        e.update({"ORG_EVIDENCE": str(ev), "ORG_KEY": org_key or task, "ORG_RUN": RUN,
                  "ORG_ALLOWED_RUNGS": "free,ordinary"})
        e.update(env or {})
        e = {k: v for k, v in e.items() if v is not None}
        script = Path(checks_dir or ROOT / "checks") / f"{name}.py"
        return subprocess.run([sys.executable, str(script), argv_key or org_key or task],
                              capture_output=True, text=True, env=e)


def run_spec(name, spec, **kw):
    return run_check(name, build(spec), **kw)


@pytest.mark.parametrize("name", sorted(SPECS))
def test_check_passes_on_good_evidence(name):
    cp = run_spec(name, SPECS[name])
    assert cp.returncode == 0, cp.stderr


CASE_IDS = [(n, i) for n in sorted(BAD) for i in range(len(BAD[n]))]


@pytest.mark.parametrize("name,i", CASE_IDS, ids=[f"{n}:{BAD[n][i][0]}" for n, i in CASE_IDS])
def test_check_fails_on_each_bad_case_and_says_why(name, i):
    label, fn = BAD[name][i]
    cp = run_spec(name, fn(copy.deepcopy(SPECS[name])))
    assert cp.returncode == 1, f"{label}: {cp.stdout}{cp.stderr}"
    assert cp.stderr.strip()


EMPTY_OK = {"tests_edited", "failed", "uncommitted", "changed"}


@pytest.mark.parametrize("name", [n for n in sorted(SPECS) if "out" in SPECS[n]])
def test_every_field_is_required_typed_and_non_empty(name):
    spec = SPECS[name]
    for field, value in spec["out"].items():
        wrong = 42 if isinstance(value, list) else ["x"]
        for label, s in (("missing", mut(spec, ["out", field], delete=True)),
                         ("wrong type", mut(spec, ["out", field], wrong))):
            assert run_spec(name, s).returncode in (1, 2), f"{name}.{field} {label}"
        if isinstance(value, (list, str, dict)) and field not in EMPTY_OK:
            assert run_spec(name, mut(spec, ["out", field], type(value)())).returncode in (1, 2), \
                f"{name}.{field} empty"
    for part in ("outputs", "steps", "decisions"):
        for k in spec.get(part, {}):
            assert run_spec(name, mut(spec, [part, k], delete=True)).returncode == 2, f"{name} lacks {part}.{k}"


@pytest.mark.parametrize("name", [n for n in sorted(SPECS) if n in FACT])
def test_a_fact_check_ignores_an_agent_claim_that_contradicts_the_code_step(name):
    # outputs hold claims; a fact check must judge `output` and `steps`, so a rosy claim changes nothing
    spec = copy.deepcopy(SPECS[name])
    spec["outputs"] = dict(spec.get("outputs", {}))
    bad = BAD[name][0][1](spec)
    bad["outputs"] = {**bad.get("outputs", {}), "claim": {"suite": {"passed": 99, "failed": 0}, "runs": []}}
    assert run_spec(name, bad).returncode == 1


# ---- the evidence contract (spec 6.1, _lib): key and run binding, exit codes


@pytest.mark.parametrize("name", sorted(SPECS))
def test_evidence_for_another_task_exits_two(name):
    ev = build(SPECS[name], key="other/key")
    cp = run_check(name, ev)
    assert cp.returncode == 2 and "key" in cp.stderr


@pytest.mark.parametrize("name", sorted(SPECS))
def test_stale_evidence_from_another_run_exits_two(name):
    cp = run_check(name, build(SPECS[name], run="r0"))
    assert cp.returncode == 2 and "run" in cp.stderr


@pytest.mark.parametrize("name", sorted(SPECS))
def test_argv_that_differs_from_org_key_exits_two(name):
    assert run_spec(name, SPECS[name], argv_key="other").returncode == 2


@pytest.mark.parametrize("name", sorted(SPECS))
def test_evidence_without_key_run_or_output_exits_two(name):
    for drop in ("key", "run", "output"):
        ev = build(SPECS[name])
        del ev[drop]
        assert run_check(name, ev).returncode == 2, drop
    ev = build(SPECS[name])
    ev["output"] = {"exit": "0", "stdout": ""}
    assert run_check(name, ev).returncode == 2


@pytest.mark.parametrize("name", sorted(SPECS))
def test_a_failed_checked_step_fails_the_check(name):
    ev = build(SPECS[name])
    ev["output"]["exit"] = 1
    cp = run_check(name, ev)
    assert cp.returncode == 1 and "exit" in cp.stderr


@pytest.mark.parametrize("name", [n for n in sorted(SPECS) if "out" in SPECS[n]])
def test_unparseable_output_exits_two(name):
    for text in ("not json", "[1]"):
        ev = build(SPECS[name])
        ev["output"]["stdout"] = text
        assert run_check(name, ev).returncode == 2


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


def test_lib_has_no_unused_test_outcomes():
    assert "TEST_OUTCOMES" not in (ROOT / "checks" / "_lib.py").read_text()


# ---- every-proposal-is-within-its-rung: change.head and change.worktree, check_change, ORG_ALLOWED_RUNGS

CHANGE_OK = (SCRIPTS / "check_change.py").is_file() and HAS_YAML and shutil.which("git") is not None
CHANGE_WHY = "needs scripts/check_change.py (U15), PyYAML and git"
needs_change = pytest.mark.skipif(not CHANGE_OK, reason=CHANGE_WHY)
CHANGE_DIRS = ("workflows", "briefs", "criteria", "schemas/org", "checks", "collectors", "bin")
CHANGE_FILES = ("manifest.json", "metrics.json")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com",
                           *args], capture_output=True, text=True, check=True).stdout.strip()


def make_repo(tmp_path, edit=None, noop=False):
    """An org root committed in a temp git repo, then edited in the working tree. Returns the evidence."""
    repo = tmp_path / "root"
    for d in CHANGE_DIRS:
        for p in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else []:
            if p.is_file() and "__pycache__" not in p.parts:
                dest = repo / p.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(p.read_bytes())
    for f in CHANGE_FILES:
        (repo / f).write_bytes((ROOT / f).read_bytes())
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    head = git(repo, "rev-parse", "HEAD")
    if edit and not noop:
        path, fn = edit
        (repo / path).write_text(fn((repo / path).read_text()))
    return {"run": RUN, "key": "propose", "output": {"exit": 0, "stdout": "free text of the agent"},
            "steps": {}, "outputs": {}, "decisions": {}, "change": {"head": head, "worktree": str(repo)}}


BRIEF = ("briefs/sw/red.md", lambda t: t + "\nOne more rule.\n")
FLOOR_CRITERIA = ("criteria/sw/spec.md", lambda t: t + "\nOne more rule.\n")
LOOP_BOUND = ("workflows/sw-development.yaml", lambda t: t.replace("{ each: build-round, in: [1, 2, 3] }", "{ each: build-round, in: [1, 2, 3, 4] }"))


@needs_change
def test_rung_check_passes_for_a_change_within_the_runtime_rungs(tmp_path):
    assert run_check(RUNG, make_repo(tmp_path, BRIEF)).returncode == 0


@needs_change
def test_rung_check_refuses_a_floor_file_and_ignores_a_claimed_rung(tmp_path):
    ev = make_repo(tmp_path, FLOOR_CRITERIA)
    ev["output"]["stdout"] = json.dumps({"rung": "free", "base": {}, "new": {"criteria/sw/spec.md": "x"}})
    cp = run_check(RUNG, ev)
    assert cp.returncode == 1 and "criteria/sw/spec.md" in cp.stderr
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": "free,ordinary,protected,frozen"}).returncode == 0


@needs_change
def test_rung_check_takes_allowed_rungs_from_the_runtime_only(tmp_path):
    ev = make_repo(tmp_path, LOOP_BOUND)
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": "free"}).returncode == 1  # a loop bound is ordinary
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": "free,ordinary"}).returncode == 0
    for bad in (None, "", "free,bogus"):
        assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": bad}).returncode == 1
    ev["allowed_rungs"] = ["free", "ordinary"]
    assert run_check(RUNG, ev, env={"ORG_ALLOWED_RUNGS": None}).returncode == 1


@needs_change
def test_rung_check_fails_when_the_change_is_empty(tmp_path):
    assert run_check(RUNG, make_repo(tmp_path, BRIEF, noop=True)).returncode == 1


@needs_change
def test_rung_check_fails_on_unusable_change(tmp_path):
    ev = make_repo(tmp_path, BRIEF)
    bad_head = copy.deepcopy(ev)
    bad_head["change"]["head"] = "0" * 40
    assert run_check(RUNG, bad_head).returncode == 1
    no_tree = copy.deepcopy(ev)
    no_tree["change"]["worktree"] = str(tmp_path / "nowhere")
    assert run_check(RUNG, no_tree).returncode == 1
    missing = copy.deepcopy(ev)
    del missing["change"]
    assert run_check(RUNG, missing).returncode == 2
    typed = copy.deepcopy(ev)
    typed["change"] = {"head": 5, "worktree": 6}
    assert run_check(RUNG, typed).returncode == 2


def test_rung_check_fails_closed_without_check_change(tmp_path):
    shutil.copytree(ROOT / "checks", tmp_path / "checks")  # no ../scripts beside the copy
    ev = build({"task": "propose", "out_raw": "x"}, change={"head": "h", "worktree": str(tmp_path)})
    cp = run_check(RUNG, ev, checks_dir=tmp_path / "checks")
    assert cp.returncode == 1 and "check_change" in cp.stderr


@pytest.mark.parametrize("name", ALL_CHECKS)
def test_every_pass_fixture_matches_the_documented_reads(name):
    readme = (ROOT / "checks" / "README.md").read_text()
    row = re.search(rf"(?m)^\| `{re.escape(name)}`\s*\|.*$", readme)
    assert row, f"{name} is not in the table of checks/README.md"
    cells = [c.strip() for c in row.group(0).strip("|").split("|")]
    assert len(cells) == 4, name
    klass, task, reads = cells[1], cells[2], cells[3]
    assert klass == ("fact" if name in FACT else "shape"), name
    if name == RUNG:
        assert "change.head" in reads and "change.worktree" in reads and "ORG_ALLOWED_RUNGS" in reads
        return
    spec = SPECS[name]
    assert f"`{spec['task'].split('#')[0]}`" in task
    for prefix, actual in (("output", set(spec.get("out", {}))), ("outputs", set(spec.get("outputs", {}))),
                           ("steps", set(spec.get("steps", {}))), ("decisions", set(spec.get("decisions", {})))):
        documented = set(re.findall(rf"(?<![a-z]){prefix}\.([A-Za-z0-9_/-]+)", reads))
        if prefix == "output" and "out_raw" in spec:
            assert "output.exit" in reads
            continue
        assert documented >= actual, (name, prefix, documented, actual)


def test_readme_states_the_contract():
    text = (ROOT / "checks" / "README.md").read_text().lower()
    for needle in ("org_evidence", "org_key", "org_run", "org_allowed_rungs", "frozen", "never from agent output",
                   "trust boundary", "summary", "not verified", "defaults taken by the orchestrator",
                   "shape", "fact", "outputs", "decisions", "change.head"):
        assert needle in text, needle
    assert "u14 adds" not in text and "sibling" not in text


@needs_yaml
def test_named_checks_match_the_fixtures():
    assert sorted(refs()["check"]) == ALL_CHECKS


@needs_yaml
def test_manifest_declares_every_check_with_the_right_class():
    manifest = load("manifest.json")
    classes = manifest["checks"]
    assert sorted(classes) == ALL_CHECKS
    assert {n for n, c in classes.items() if c == "fact"} == FACT
    assert {p.stem for p in (ROOT / "checks").glob("*.py") if not p.name.startswith("_")} == set(classes)
    for name in WORKFLOWS:
        for path, body in all_leaves(name):
            org = body["metadata"]["org"]
            for item in org.get("acceptance", []):
                if classes.get(item.get("check")) == "fact":
                    assert org["by"] == "code", f"fact check {item['check']} sits on {name}:{path}, not a code step"


@needs_yaml
def test_improver_role_declares_its_rungs():
    assert load("manifest.json")["roles"]["improver"]["rungs"] == ["free", "ordinary"]


@needs_yaml
def test_tdd_unit_moves_fact_checks_onto_code_steps_and_samples_the_model_steps():
    leaves_ = dict(all_leaves("tdd-unit"))
    def acc(p):
        return leaves_[f"cycle/{p}"]["metadata"]["org"]["acceptance"]
    assert [i.get("check") for i in acc("red-evidence")] == [
        "red-evidence", "new-test-fails-on-an-assertion-not-a-compile-error"]
    assert [i.get("check") for i in acc("green-evidence")] == ["green-evidence", "suite-green-and-no-test-edited"]
    assert [i.get("check") for i in acc("refactor-evidence")] == ["suite-still-green-and-no-test-edited"]
    for step in ("red", "green", "refactor"):
        assert acc(step) == [{"rubric": f"criteria/sw/{step}.md", "judge": "reviewer", "sample": 0.2}]
    assert leaves_["cycle/refactor-evidence"]["metadata"]["org"]["by"] == "code"


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
        assert "not implemented" not in f.read_text()  # U14 built both; test_cycle.py runs them


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


def test_acceptance_test_ids_are_pytest_node_ids():
    brief = (ROOT / "briefs" / "sw" / "acceptance-tests.md").read_text()
    rubric = (ROOT / "criteria" / "sw" / "acceptance-tests.md").read_text()
    for text in (brief, rubric):
        assert "pytest node id" in text and "tests/test_x.py::test_y" in text


def test_readme_says_no_check_reads_fanned_out_work():
    text = (ROOT / "checks" / "README.md").read_text()
    assert "No check or rubric reads the result of fanned-out work" in text


def test_acceptance_tests_brief_scopes_edge_cases():
    assert "where meaningful" in (ROOT / "briefs" / "sw" / "acceptance-tests.md").read_text()


def test_briefs_are_not_empty():
    briefs = sorted((ROOT / "briefs" / "sw").glob("*.md"))
    assert len(briefs) == 15
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
        for r in rules:  # a judge sees only the item, the task output and the evidence of code steps
            cited = r.split("Judged against:")[1]
            assert re.search(r"\b(item|output|outputs|evidence|diff|steps)\b", cited), f"{rel}: {cited}"
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
    assert "one after another" in text and "disjoint" in text
    assert "not in parallel" not in text


def test_improve_brief_follows_the_rung_table_and_never_asks_for_a_rung():
    text = (ROOT / "briefs" / "sw" / "improve.md").read_text()
    assert "state the rung" not in text.lower() and "rung each" not in text.lower()
    assert "you write files only" in text.lower()
    assert "base" not in text.lower().replace("baseline", "") and "worktree" not in text.lower()
    for needle in ("ordinary", "frozen", "protected", "floor task"):
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


# ---------------------------------------------------------------- spec update 12 (P55, P57, P59)


@pytest.mark.parametrize("name", ["red-evidence", "new-test-fails-on-an-assertion-not-a-compile-error"])
@pytest.mark.parametrize("outcome", ["import-error", "error"])
def test_p59_red_accepts_a_missing_symbol_only_when_the_unit_declares_new_symbols(name, outcome):
    spec = mut(SPECS[name], ["out", "runs", 0, "outcome"], outcome)
    assert run_spec(name, spec).returncode == 1
    spec = mut(spec, ["input", "unit", "new_symbols"], ["add"])
    cp = run_spec(name, spec)
    assert cp.returncode == 0, cp.stderr


@pytest.mark.parametrize("name", ["red-evidence", "new-test-fails-on-an-assertion-not-a-compile-error"])
def test_p59_new_symbols_must_be_a_list_of_names(name):
    spec = mut(mut(SPECS[name], ["out", "runs", 0, "outcome"], "import-error"), ["input", "unit", "new_symbols"], "add")
    assert run_spec(name, spec).returncode in (1, 2)


@pytest.mark.parametrize("drop", ["unit", "write_set"])
def test_p57_red_fact_without_a_write_set_is_missing_evidence(drop):
    spec = copy.deepcopy(SPECS["red-evidence"])
    if drop == "unit":
        spec["input"] = {}
    else:
        del spec["input"]["unit"]["write_set"]
    cp = run_spec("red-evidence", spec)
    assert cp.returncode == 2 and "write_set" in cp.stderr


def test_p57_a_changed_file_outside_the_write_set_is_not_the_red_checks_business():
    spec = mut(SPECS["red-evidence"], ["out", "changed"], ["test_add.py", "other.py"])
    assert run_spec("red-evidence", spec).returncode == 0


def test_p57_the_red_brief_tells_a_rework_round_to_restore_the_production_files():
    text = (ROOT / "briefs" / "sw" / "red.md").read_text()
    assert "git checkout" in text and "rework round" in text


def test_p55_judge_criteria_read_the_write_set_from_the_workflow_input_not_the_cut_output():
    for name in ("green", "refactor", "unit-review"):
        text = (ROOT / "criteria" / "sw" / f"{name}.md").read_text()
        assert "cut output" not in text, name
        assert "write_set" in text, name


@needs_schema
def test_p59_the_cut_schema_accepts_new_symbols_and_the_cut_brief_asks_for_them():
    import jsonschema
    schema = load("schemas/org/units.json")
    unit = dict(UNITS["units"][0], new_symbols=["add"])
    jsonschema.validate({"units": [unit]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"units": [dict(unit, new_symbols="add")]}, schema)
    assert "new_symbols" in (ROOT / "briefs" / "sw" / "cut.md").read_text()


@pytest.mark.parametrize("step,later", [("red", "red-evidence"), ("green", "green-evidence"),
                                        ("refactor", "refactor-evidence")])
def test_p56_a_step_rubric_cites_no_fact_of_the_evidence_step_that_runs_after_its_judge(step, later):
    # the judge runs when the model step ends; the next evidence step has not run, so its output cannot be cited
    text = (ROOT / "criteria" / "sw" / f"{step}.md").read_text()
    assert later not in text and "evidence.change.diff" in text


def test_p60_the_refactor_criteria_let_a_no_op_refactor_pass():
    assert "changes nothing passes" in " ".join((ROOT / "criteria" / "sw" / "refactor.md").read_text().split())
