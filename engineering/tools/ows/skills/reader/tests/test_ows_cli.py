"""Tests for the ows library API and the ows.py command line (validate, tasks, floors)."""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
CLI = os.path.join(SCRIPTS, "ows.py")
VALIDATE_ORG = os.path.join(SCRIPTS, "ows", "validate_org.py")
FIX = os.path.join(HERE, "fixtures", "validate_org")
sys.path.insert(0, SCRIPTS)

import ows  # noqa: E402


def fx(name):
    return os.path.join(FIX, name)


SHIP, LOOP, CAT, MAN = fx("ship.json"), fx("unit-loop.json"), fx("catalog.json"), fx("manifest.json")

SHIP_TASKS = [
    ("frame", "step", False),
    ("spec", "step", True),
    ("checks-fail", "step", False),
    ("plan", "step", False),
    ("build", "container", False),
    ("build/units", "container", False),
    ("build/units/implement", "call", False),
    ("build/checks-pass", "step", False),
    ("gave-up", "escalation", False),
    ("review", "step", True),
    ("release-gate", "gate", True),
    ("release", "step", False),
    ("report", "emit", False),
    ("retro", "call", False),
]


def run(*args, script=CLI):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True, timeout=120)


def write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def ship():
    with open(SHIP, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- library


def test_library_tasks_lists_keys_kinds_and_floors_in_pre_order():
    rows = ows.tasks(ows.load(SHIP))
    assert [(r["key"], r["kind"], r["floor"]) for r in rows] == SHIP_TASKS


def test_library_tasks_rows_carry_the_org_fields():
    rows = {r["key"]: r for r in ows.tasks(ows.load(SHIP))}
    assert rows["frame"] == {"key": "frame", "kind": "step", "by": "model", "role": "pm", "brief": "briefs/frame.md",
                             "floor": False, "acceptance": [{"rubric": "criteria/frame.md", "judge": "lead"}],
                             "metrics": ["escalations"], "calls": None}
    assert rows["build/units/implement"]["calls"] == "unit-loop"
    assert rows["build"]["by"] is None and rows["build"]["metrics"] is None


def test_library_floors_without_and_with_a_manifest():
    doc, man = ows.load(SHIP), ows.load(MAN)
    plain = [r["key"] for r in ows.floors(doc)]
    assert plain == ["spec", "review", "release-gate"]
    assert [r["key"] for r in ows.floors(doc, man)] == plain
    man["workflows"]["unit-loop"]["floors"] = ["red"]
    rows = ows.floors(doc, man)
    assert [r["key"] for r in rows] == ["spec", "build/units/implement", "review", "release-gate"]
    assert rows[1] == {"key": "build/units/implement", "kind": "call", "calls": "unit-loop"}


def test_library_validate_matches_validate_org():
    doc, cat, man = ows.load(SHIP), ows.load(CAT), ows.load(MAN)
    assert ows.validate(doc, cat, man) == []
    doc["do"][0]["frame"]["metadata"]["org"]["by"] = "robot"
    assert ows.validate(doc, cat, man) == ows.validate_org.validate_org(doc, cat, man) != []


@pytest.mark.parametrize("doc", [None, [], "x", {"do": "x"}, {"do": [1, {"a": 1}, {"b": {"run": 1}}]}])
def test_library_readers_never_raise(doc):
    assert isinstance(ows.tasks(doc), list) and isinstance(ows.floors(doc, {"workflows": 3}), list)


def test_library_load_errors_are_ows_errors(tmp_path):
    bad = tmp_path / "w.json"
    bad.write_text('{"a": 1, "a": 2}')
    with pytest.raises(ows.LoadError):
        ows.load(str(bad))
    with pytest.raises(ows.UsageError):
        ows.load(str(tmp_path / "w.txt"))


# ---------------------------------------------------------------- tasks and floors


def test_cli_tasks_prints_key_kind_and_floor_in_pre_order():
    p = run("tasks", SHIP)
    assert (p.returncode, p.stderr) == (0, "")
    want = ["\t".join([k, kind] + (["floor"] if floor else [])) for k, kind, floor in SHIP_TASKS]
    assert p.stdout.splitlines() == want


def test_cli_tasks_json():
    p = run("tasks", SHIP, "--json")
    assert p.returncode == 0
    rows = json.loads(p.stdout)
    assert [(r["key"], r["kind"], r["floor"]) for r in rows] == SHIP_TASKS


def test_cli_floors_text_and_json():
    p = run("floors", SHIP)
    assert (p.returncode, p.stdout) == (0, "spec\tstep\nreview\tstep\nrelease-gate\tgate\n")
    p = run("floors", SHIP, "--manifest", MAN, "--json")
    assert p.returncode == 0
    assert [r["key"] for r in json.loads(p.stdout)] == ["spec", "review", "release-gate"]


def test_cli_floors_counts_a_call_to_a_workflow_with_floors(tmp_path):
    with open(MAN, encoding="utf-8") as f:
        man = json.load(f)
    man["workflows"]["unit-loop"]["floors"] = ["red"]
    p = run("floors", SHIP, "--manifest", write(tmp_path, "m.json", man))
    assert p.stdout.splitlines()[1] == "build/units/implement\tcall\tunit-loop"


# ---------------------------------------------------------------- validate: same output as validate_org.py


def _variants(tmp_path):
    bad_by = ship()
    bad_by["do"][0]["frame"]["metadata"]["org"]["by"] = "robot"
    unknown_doc_key = ship()
    unknown_doc_key["document"]["metadata"]["org"]["governance"] = "workflow"
    dup = tmp_path / "dup.json"
    dup.write_text('{"a": 1, "a": 2}')
    return [
        [SHIP, LOOP],
        [SHIP],
        [write(tmp_path, "bad-by.json", bad_by)],
        [write(tmp_path, "unknown-doc-key.json", unknown_doc_key), LOOP],
        [str(dup)],
        [str(tmp_path / "missing.json")],
        [str(tmp_path / "w.txt")],
    ]


def test_cli_validate_prints_the_same_lines_and_code_as_validate_org(tmp_path):
    for workflows in _variants(tmp_path):
        args = ["--catalog", CAT, "--manifest", MAN, *workflows]
        mine, theirs = run("validate", *args), run(*args, script=VALIDATE_ORG)
        assert (mine.returncode, mine.stdout, mine.stderr) == (theirs.returncode, theirs.stdout, theirs.stderr), workflows


def test_cli_validate_valid_is_silent_and_exits_0():
    p = run("validate", "--catalog", CAT, "--manifest", MAN, SHIP, LOOP)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


@pytest.mark.parametrize("mutate,line", [
    (lambda d: d["document"]["metadata"]["org"].__setitem__("governance", "workflow"),
     "document.metadata.org: unknown key 'governance'"),
    (lambda d: d.__setitem__("contract", {}), "contract: unknown top-level key"),
    (lambda d: d["document"]["metadata"].__setitem__("x-team", {}),
     "document.metadata: unknown namespace 'x-team'; only 'org' is allowed"),
], ids=["org-key", "top-level-key", "metadata-namespace"])
def test_cli_validate_unknown_document_key_fails(tmp_path, mutate, line):
    doc = ship()
    mutate(doc)
    f = write(tmp_path, "w.json", doc)
    p = run("validate", "--catalog", CAT, "--manifest", MAN, f)
    assert p.returncode == 1
    assert f"ERROR: {f}: {line}" in p.stderr.splitlines()


def test_cli_validate_json(tmp_path):
    p = run("validate", "--catalog", CAT, "--manifest", MAN, SHIP, "--json")
    assert (p.returncode, json.loads(p.stdout)) == (0, {"errors": []})
    doc = ship()
    doc["do"][0]["frame"]["metadata"]["org"]["by"] = "robot"
    f = write(tmp_path, "w.json", doc)
    p = run("validate", "--catalog", CAT, "--manifest", MAN, f, "--json")
    assert p.returncode == 1
    assert json.loads(p.stdout) == {"errors": [f"{f}: frame: metadata.org.by: 'robot' is not one of code, human, model"]}


def test_cli_validate_json_reports_load_and_catalog_errors(tmp_path):
    dup = tmp_path / "dup.json"
    dup.write_text('{"a": 1, "a": 2}')
    p = run("validate", "--catalog", CAT, "--manifest", MAN, str(dup), "--json")
    assert (p.returncode, json.loads(p.stdout)) == (1, {"errors": [f"{dup}: duplicate key 'a'"]})
    with open(CAT, encoding="utf-8") as fh:
        cat = json.load(fh)
    b = write(tmp_path, "b.json", {"cycle-time": cat["cycle-time"]})
    p = run("validate", "--catalog", CAT, "--catalog", b, "--manifest", MAN, SHIP, "--json")
    assert (p.returncode, json.loads(p.stdout)) == (1, {"errors": [f"catalog: cycle-time: defined in {CAT} and {b}"]})


def test_cli_yaml_workflow(tmp_path):
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed")
    f = tmp_path / "ship.yaml"
    f.write_text(yaml.safe_dump(ship()), encoding="utf-8")
    assert run("tasks", str(f)).stdout == run("tasks", SHIP).stdout
    p = run("validate", "--catalog", CAT, "--manifest", MAN, str(f))
    assert (p.returncode, p.stderr) == (0, "")


# ---------------------------------------------------------------- exit codes


@pytest.mark.parametrize("args", [
    [], ["bogus"], ["tasks"], ["floors"], ["validate", SHIP], ["validate", "--catalog", CAT, SHIP],
    ["tasks", SHIP, "--bogus"],
], ids=["none", "unknown-command", "tasks-no-file", "floors-no-file", "validate-no-catalog",
        "validate-no-manifest", "unknown-flag"])
def test_cli_usage_errors_exit_2(args):
    assert run(*args).returncode == 2


@pytest.mark.parametrize("command", ["tasks", "floors"])
def test_cli_readers_unknown_extension_exits_2_and_load_error_exits_1(tmp_path, command):
    txt = tmp_path / "w.txt"
    txt.write_text("{}")
    assert run(command, str(txt)).returncode == 2
    p = run(command, str(tmp_path / "missing.json"))
    assert p.returncode == 1 and p.stderr.startswith("ERROR: ") and p.stdout == ""


def test_cli_floors_manifest_load_error_exits_1(tmp_path):
    p = run("floors", SHIP, "--manifest", str(tmp_path / "missing.json"))
    assert p.returncode == 1 and p.stderr.startswith("ERROR: ")


def test_cli_validate_unknown_extension_exits_2(tmp_path):
    txt = tmp_path / "w.txt"
    txt.write_text("{}")
    assert run("validate", "--catalog", CAT, "--manifest", MAN, str(txt)).returncode == 2
    assert run("validate", "--catalog", CAT, "--manifest", MAN, str(txt), "--json").returncode == 2


def test_cli_tasks_lists_a_workflow_that_does_not_validate(tmp_path):
    doc = ship()
    doc["do"][0]["frame"]["metadata"]["org"]["by"] = "robot"
    p = run("tasks", write(tmp_path, "w.json", doc))
    assert p.returncode == 0 and p.stdout.splitlines()[0] == "frame\tstep"
