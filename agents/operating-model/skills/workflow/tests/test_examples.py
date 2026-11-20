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

WORKFLOWS = ["sw-development", "tdd-unit", "improve"]
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
        assert sorted(manifest["workflows"][name]["floors"]) == sorted(floors)
    assert sorted(manifest["workflows"]["sw-development"]["floors"]) == ["merge-gate", "review", "spec"]


# ---------------------------------------------------------------- 2. every reference resolves


@needs_yaml
def test_references_resolve_to_files():
    r = refs()
    assert len(r["brief"]) == 11 and len(r["rubric"]) == 6 and len(r["schema"]) == 2
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
}
GREEN = {"suite": {"passed": 12, "failed": 0}, "tests_edited": []}
ASSERT_RUNS = {"runs": [{"test": "t1", "outcome": "assertion"}, {"test": "t2", "outcome": "assertion"}]}
BAD_RUNS = {"runs": [{"test": "t1", "outcome": "assertion"}, {"test": "t2", "outcome": "compile-error"}]}
REPORT_OK = "\n".join(f"## {h}\ntext" for h in
                      ["Summary", "Acceptance", "Tests", "Defects", "Metrics", "Not verified"])
CASES = {
    "spec-check": ({"item": ITEM}, {"item": {**ITEM, "criteria": []}}),
    "spec-coverage": (
        {"item": ITEM, "tests": [{"id": "a", "criteria": ["C1"]}, {"id": "b", "criteria": ["C2"]}]},
        {"item": ITEM, "tests": [{"id": "a", "criteria": ["C1"]}]},
    ),
    "every-acceptance-test-fails-on-an-assertion": (ASSERT_RUNS, BAD_RUNS),
    "red-evidence": (ASSERT_RUNS, {"runs": []}),
    "new-test-fails-on-an-assertion-not-a-compile-error": (ASSERT_RUNS, BAD_RUNS),
    "green-evidence": (GREEN, {**GREEN, "suite": {"passed": 11, "failed": 1}}),
    "suite-green-and-no-test-edited": (GREEN, {**GREEN, "tests_edited": ["tests/test_a.py"]}),
    "suite-still-green-and-no-test-edited": (GREEN, {**GREEN, "tests_edited": ["tests/test_a.py"]}),
    "write-sets-are-disjoint": (
        {"units": [{"id": "u1", "write_set": ["a.py"]}, {"id": "u2", "write_set": ["b.py"]}]},
        {"units": [{"id": "u1", "write_set": ["src/"]}, {"id": "u2", "write_set": ["src/b.py"]}]},
    ),
    "unit-verdict-is-pass": ({"verdict": "pass"}, {"verdict": "fail"}),
    "acceptance-suite-green": (GREEN, {"suite": {"passed": 0, "failed": 0}, "tests_edited": []}),
    "checks-green-and-gate-approved": (
        {"ci": {"state": "success"}, "gate": {"decision": "approve"}},
        {"ci": {"state": "success"}, "gate": {"decision": "reject"}},
    ),
    "report-has-every-required-section": (
        {"report": REPORT_OK}, {"report": REPORT_OK.replace("## Metrics\ntext\n", "")}
    ),
    "every-proposal-is-within-its-rung": (
        {"allowed_rungs": ["free"], "proposals": [{"id": "p1", "rung": "free"}]},
        {"allowed_rungs": ["free"], "proposals": [{"id": "p1", "rung": "frozen"}]},
    ),
}


def run_check(name, evidence, key="some/key"):
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "evidence.json"
        ev.write_text(json.dumps(evidence))
        env = {**os.environ, "ORG_EVIDENCE": str(ev)}
        return subprocess.run([sys.executable, str(ROOT / "checks" / f"{name}.py"), key],
                              capture_output=True, text=True, env=env)


@pytest.mark.parametrize("name", sorted(CASES))
def test_check_passes_on_good_evidence(name):
    good, _ = CASES[name]
    cp = run_check(name, good)
    assert cp.returncode == 0, cp.stderr


@pytest.mark.parametrize("name", sorted(CASES))
def test_check_fails_on_bad_evidence_and_says_why(name):
    _, bad = CASES[name]
    cp = run_check(name, bad)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert cp.stderr.strip()


@pytest.mark.parametrize("name", sorted(CASES))
def test_check_fails_when_evidence_is_missing(name):
    cp = subprocess.run([sys.executable, str(ROOT / "checks" / f"{name}.py"), "k"], capture_output=True,
                        text=True, env={k: v for k, v in os.environ.items() if k != "ORG_EVIDENCE"})
    assert cp.returncode != 0


@needs_yaml
def test_every_named_check_has_a_fixture_pair():
    assert sorted(refs()["check"]) == sorted(CASES)


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
    assert len(briefs) == 11
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
