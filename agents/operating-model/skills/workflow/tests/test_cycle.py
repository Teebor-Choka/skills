"""Acceptance tests for the complete software process (U14).

Every flow test runs the shipped workflows on the interpreter with a ScriptedHost: no model, a virtual
clock, scripted step output, check results and owner decisions. One test per row of the overview's loop
table, plus the adversarial cases. The evidence programs (`bin/tdd-evidence`, `bin/merge-change`) are run
for real on a temporary git repository.

Flow tests read YAML and skip without PyYAML. Run with:
uv run --with pytest --with pyyaml --with jsonschema python -m pytest <this file> -q
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_catalog as vc  # noqa: E402
from interpreter import Interpreter, ScriptedHost, StepOutcome  # noqa: E402

RID = "0123456789abcdef0123456789abcdef"
HAS_YAML = importlib.util.find_spec("yaml") is not None
needs_yaml = pytest.mark.skipif(not HAS_YAML, reason="optional: uv run --with pyyaml")

NAMES = ["sw-development", "tdd-unit", "improve", "bug", "improvement-scan"]
SPEC = "spec-cycle/spec"
DESIGN = "spec-cycle/design-cycle/design"
FEAS = "spec-cycle/design-cycle/feasibility"
CUT = "spec-cycle/design-cycle/cut"
LAYER = "spec-cycle/design-cycle/build-cycle/layer-run"
SYSTEM = "spec-cycle/design-cycle/system-run"
REVIEW = "review-cycle/review"


def load(rel):
    return vc.load_document(str(ROOT / rel))


def workflows():
    return {n: load(f"workflows/{n}.yaml") for n in NAMES}


def check_names(wfs):
    names = set()

    def walk(lst):
        for item in lst:
            (_, t), = item.items()
            for i in ((t.get("metadata") or {}).get("org") or {}).get("acceptance", []):
                if "check" in i:
                    names.add(i["check"])
            for k in ("do", "try"):
                if isinstance(t.get(k), list):
                    walk(t[k])
    for doc in wfs.values():
        walk(doc["do"])
    return names


def event(type_, data=None, signature="owner"):
    return {"type": type_, "data": dict(data or {}), "signature": signature}


def decide(task, decision="approve", item=None, run=RID):
    d = {"run": run, "task": task, "decision": decision}
    if item is not None:
        d["item"] = item
    return event("org.owner-decided", d)


class Scn:
    """Scripted outputs per step key, scripted check results per task key, owner decisions."""

    def __init__(self, outs=None, acc=None, reviews=("approve",), gate="approve", extra_events=(), gate_key="merge-gate",
                 review_key=REVIEW):
        base = {
            CUT: {"units": [{"id": "u1"}, {"id": "u2"}]},
            FEAS: {"feasible": True},
            LAYER: {"layer_fault": "none"},
            SYSTEM: {"system_fault": "none"},
        }
        base.update(outs or {})
        self.steps = {}
        for k, v in base.items():
            vals = v if isinstance(v, list) else [v]
            self.steps[k] = [StepOutcome(output=o, stdout=json.dumps(o)) for o in vals]
        self.acc = {k: list(v) if isinstance(v, list) else [v] for k, v in (acc or {}).items()}
        self.n = {}
        events = [(10 * (i + 1), decide(review_key, d, item=0)) for i, d in enumerate(reviews)]
        events.append((1000, decide(gate_key, gate)))
        events += list(extra_events)
        self.events = events

    def check(self, name, key, evidence):
        base = re.sub(r"#[0-9]+", "", key)
        for cand in (base, base.rsplit(">", 1)[-1]):
            if cand in self.acc:
                i = self.n.get(cand, 0)
                self.n[cand] = i + 1
                seq = self.acc[cand]
                return seq[min(i, len(seq) - 1)]
        return True

    def host(self, wfs):
        return ScriptedHost(steps=self.steps, checks={n: self.check for n in check_names(wfs)}, events=self.events)


def run(name, scn=None, **kw):
    wfs = workflows()
    scn = scn or Scn(**kw)
    host = scn.host(wfs)
    res = Interpreter(wfs, host, catalog=load("metrics.json"), manifest=load("manifest.json")).run(name, run_id=RID)
    return res, host


def n_starts(res, pattern):
    return len([e for e in res.events if e["kind"] == "task-start" and re.fullmatch(pattern, e["key"])])


def emitted(res, type_):
    return [e["event"] for e in res.events if e["kind"] == "emit" and e["event"]["type"] == type_]


def order(res, *keys):
    first = {}
    for i, e in enumerate(res.events):
        if e["kind"] == "task-start":
            first.setdefault(e["key"], i)
    return [first[k] for k in keys]


UNITS = r"spec-cycle/design-cycle/build-cycle/units/tdd#[0-9]+"


# ---------------------------------------------------------------- the five workflows are valid and acyclic


@needs_yaml
def test_every_workflow_file_exists_and_is_in_the_manifest():
    man = load("manifest.json")
    for n in NAMES:
        assert (ROOT / "workflows" / f"{n}.yaml").is_file(), n
        assert n in man["workflows"], n


@needs_yaml
def test_every_workflow_passes_validate_org_and_the_start_graph_is_acyclic():
    cp = subprocess.run([sys.executable, str(SCRIPTS / "validate_manifest.py"), "--root", str(ROOT), "--catalog",
                         str(ROOT / "metrics.json"), str(ROOT / "manifest.json")], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    for n in NAMES:
        cp = subprocess.run([sys.executable, str(SCRIPTS / "validate_org.py"), "--catalog", str(ROOT / "metrics.json"),
                             "--manifest", str(ROOT / "manifest.json"), str(ROOT / "workflows" / f"{n}.yaml")],
                            capture_output=True, text=True)
        assert cp.returncode == 0, (n, cp.stderr)


@needs_yaml
def test_start_events_form_the_chain_scan_to_feature_to_bug():
    wfs = workflows()

    def start(n):
        return wfs[n]["schedule"]["on"]["one"]["with"]["type"]
    assert start("sw-development") == "org.work-item-ready"
    assert start("bug") == "org.bug-reported"
    assert start("improvement-scan") == "org.scan-requested"
    assert emitted_types(wfs["improvement-scan"]) == {"org.work-item-ready"}
    assert {"org.bug-reported", "org.lessons-recorded"} <= emitted_types(wfs["sw-development"])
    assert not (emitted_types(wfs["bug"]) & {"org.work-item-ready", "org.bug-reported", "org.scan-requested"})


def emitted_types(doc):
    out = set()

    def walk(lst):
        for item in lst:
            (_, t), = item.items()
            if "emit" in t:
                out.add(t["emit"]["event"]["with"]["type"])
            for k in ("do", "try"):
                if isinstance(t.get(k), list):
                    walk(t[k])
    walk(doc["do"])
    return out


# ---------------------------------------------------------------- the straight path


@needs_yaml
def test_a_clean_feature_run_goes_through_every_stage_once_and_succeeds():
    res, _ = run("sw-development")
    assert res.status == "success", res.errors
    for key in ("align", SPEC, DESIGN, FEAS, CUT, LAYER, SYSTEM, REVIEW, "merge-gate", "merge", "deploy", "verify"):
        assert n_starts(res, re.escape(key)) == 1, key
    o = order(res, "align", SPEC, DESIGN, FEAS, CUT, LAYER, SYSTEM, REVIEW, "merge-gate", "merge", "deploy", "verify")
    assert o == sorted(o)
    assert emitted(res, "org.bug-reported") == []
    assert n_starts(res, UNITS) == 2


# ---------------------------------------------------------------- loop table, one test per row


@needs_yaml
def test_row_feasibility_a_failed_check_goes_back_to_spec():  # [A] 1
    res, _ = run("sw-development", Scn(acc={FEAS: [False, True]}, outs={FEAS: [{"feasible": False}, {"feasible": True}]}))
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(SPEC)) == 2
    assert n_starts(res, re.escape(DESIGN)) == 2
    assert n_starts(res, re.escape(CUT)) == 1  # nothing was cut from the unbuildable design
    assert n_starts(res, UNITS) == 2


@needs_yaml
def test_row_feasibility_the_check_decides_not_the_loop():  # contrast: a pass never reopens spec
    res, _ = run("sw-development")
    assert n_starts(res, re.escape(SPEC)) == 1


@needs_yaml
def test_row_feasibility_that_never_holds_is_bounded_and_ends_in_error():  # [A] 1
    res, _ = run("sw-development", Scn(acc={FEAS: False}))
    assert res.status == "error"
    assert n_starts(res, re.escape(SPEC)) == 3
    assert n_starts(res, UNITS) == 0
    assert n_starts(res, "review-cycle/review") == 0 or any("acceptance failed" in e for e in res.errors)
    assert any(e.startswith(FEAS) or e.startswith(SPEC) or e.startswith("not-accepted") for e in res.errors)


@needs_yaml
def test_row_unit_a_gap_in_the_unit_goes_back_to_the_unit_test():
    scn = Scn(acc={LAYER: [False, True]}, outs={LAYER: [{"layer_fault": "unit"}, {"layer_fault": "none"}]})
    res, _ = run("sw-development", scn)
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(LAYER)) == 2
    assert n_starts(res, UNITS) == 4
    assert n_starts(res, re.escape(SPEC)) == 1 and n_starts(res, re.escape(DESIGN)) == 1


@needs_yaml
def test_row_layer_an_interface_or_criteria_error_goes_back_to_design():
    scn = Scn(acc={LAYER: [False, True]}, outs={LAYER: [{"layer_fault": "design"}, {"layer_fault": "none"}]})
    res, _ = run("sw-development", scn)
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(DESIGN)) == 2 and n_starts(res, re.escape(CUT)) == 2
    assert n_starts(res, UNITS) == 4
    assert n_starts(res, re.escape(SPEC)) == 1
    assert n_starts(res, re.escape(SYSTEM)) == 1  # system acceptance waits for green layers


@needs_yaml
def test_row_system_the_cut_or_design_is_wrong_goes_back_to_design():  # [A] 3
    scn = Scn(acc={SYSTEM: [False, True]}, outs={SYSTEM: [{"system_fault": "design"}, {"system_fault": "none"}]})
    res, _ = run("sw-development", scn)
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(DESIGN)) == 2 and n_starts(res, re.escape(SPEC)) == 1


@needs_yaml
def test_row_system_the_spec_is_wrong_goes_back_to_spec():  # [A] 3: same failure, other declared condition
    scn = Scn(acc={SYSTEM: [False, True]}, outs={SYSTEM: [{"system_fault": "spec"}, {"system_fault": "none"}]})
    res, _ = run("sw-development", scn)
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(SPEC)) == 2 and n_starts(res, re.escape(DESIGN)) == 2


@needs_yaml
def test_system_acceptance_that_never_passes_raises_not_accepted():
    res, _ = run("sw-development", Scn(acc={SYSTEM: False}, outs={SYSTEM: {"system_fault": "design"}}))
    assert res.status == "error"
    assert n_starts(res, re.escape(DESIGN)) == 3
    assert n_starts(res, "not-accepted") == 1
    assert n_starts(res, re.escape(REVIEW)) == 0


@needs_yaml
def test_row_review_a_defect_goes_back_to_the_layer_test():
    res, _ = run("sw-development", Scn(reviews=("reject", "approve")))
    assert res.status == "success", res.errors
    assert n_starts(res, re.escape(REVIEW)) == 2
    assert n_starts(res, "review-cycle/rework-units/tdd#[0-9]+") == 2  # the units run again, once
    assert n_starts(res, "review-cycle/rework-layer-run") == 1
    assert n_starts(res, re.escape(SPEC)) == 1 and n_starts(res, re.escape(DESIGN)) == 1


@needs_yaml
def test_review_that_is_never_approved_ends_in_error_before_the_merge_gate():
    res, _ = run("sw-development", Scn(reviews=("reject", "reject")))
    assert res.status == "error"
    assert n_starts(res, "merge-gate") == 0 and n_starts(res, "merge") == 0


@needs_yaml
def test_row_deploy_a_failed_verification_starts_the_bug_workflow():  # [A] 4
    res, _ = run("sw-development", Scn(acc={"verify": False}))
    sent = emitted(res, "org.bug-reported")
    assert len(sent) == 1 and sent[0]["data"]["run"] == RID
    start = load("workflows/bug.yaml")["schedule"]["on"]["one"]["with"]["type"]
    assert sent[0]["type"] == start
    bug, _ = run("bug")  # the event starts a run of the workflow it names
    assert bug.status == "success", bug.errors


@needs_yaml
def test_a_verified_deploy_starts_no_bug():
    res, _ = run("sw-development")
    assert emitted(res, "org.bug-reported") == [] and n_starts(res, "bug-report") == 0


@needs_yaml
def test_row_reflect_starts_the_next_align_by_event():
    res, _ = run("sw-development")
    sent = emitted(res, "org.lessons-recorded")
    assert len(sent) == 1 and sent[0]["data"]["run"] == RID
    assert order(res, "verify", "reflect") == sorted(order(res, "verify", "reflect"))
    # An outside mapper turns the lessons into the next work item; the next run starts at align.
    nxt, _ = run("sw-development")
    first = [e["key"] for e in nxt.events if e["kind"] == "task-start"][0]
    assert first == "align"
    assert load("workflows/sw-development.yaml")["schedule"]["on"]["one"]["with"]["type"] == "org.work-item-ready"


# ---------------------------------------------------------------- bug path


@needs_yaml
def test_bug_run_reproduces_before_it_fixes_and_reviews():
    res, _ = run("bug", Scn(review_key="review-cycle/review"))
    assert res.status == "success", res.errors
    o = order(res, "reproduce", "reproduce-evidence", "fix", "acceptance-run", REVIEW, "merge-gate", "deploy", "verify")
    assert o == sorted(o)


@needs_yaml
def test_bug_without_a_committed_failing_test_never_reaches_review():  # [A] 7
    res, host = run("bug", Scn(acc={"reproduce-evidence": False}))
    assert res.status == "error"
    assert n_starts(res, "reproduce-evidence") == 1
    assert n_starts(res, "fix") == 0
    assert not [c for c in host.calls if "review" in c[2]]
    assert res.errors[0] == "reproduce-evidence: acceptance failed"


@needs_yaml
def test_bug_reproduce_evidence_is_a_floor_in_the_manifest():
    man = load("manifest.json")
    assert "reproduce-evidence" in man["workflows"]["bug"]["floors"]
    assert "review-cycle/review" in man["workflows"]["bug"]["floors"]


@needs_yaml
def test_a_failed_deploy_verification_in_a_bug_run_raises_and_starts_nothing():
    res, _ = run("bug", Scn(acc={"verify": False}))
    assert res.status == "error"
    assert emitted(res, "org.bug-reported") == []  # no loop: the start graph stays acyclic


# ---------------------------------------------------------------- improvement scan


@needs_yaml
def test_improvement_scan_files_a_work_item_that_starts_the_feature_workflow():
    res, _ = run("improvement-scan")
    assert res.status == "success", res.errors
    sent = emitted(res, "org.work-item-ready")
    assert len(sent) == 1


# ---------------------------------------------------------------- bin/tdd-evidence on a real git repository

TDD = ROOT / "bin" / "tdd-evidence"
MERGE = ROOT / "bin" / "merge-change"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e", "-c", "user.name=t", *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (r / "test_old.py").write_text("from calc import add\n\ndef test_old():\n    assert add(1, 1) == 2\n")
    git(r, "add", "calc.py", "test_old.py")
    git(r, "commit", "-q", "-m", "base")
    return r


def tdd(repo, *args, stdin="", **env):
    e = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_BASE": git(repo, "rev-parse", "HEAD~0"),
         "PYTHONDONTWRITEBYTECODE": "1"}
    e.update(env)
    return subprocess.run([sys.executable, str(TDD), *args], input=stdin, capture_output=True, text=True, env=e)


def out(cp):
    assert cp.returncode == 0, cp.stderr
    return json.loads(cp.stdout)


def test_unit_red_reports_a_new_failing_test_as_an_assertion(repo):
    (repo / "test_new.py").write_text("from calc import add\n\ndef test_neg():\n    assert add(-1, -1) == -3\n")
    ev = out(tdd(repo, "unit", "red"))
    assert ev["runs"] == [{"test": "test_new.py::test_neg", "outcome": "assertion"}]


def test_unit_red_reports_an_import_error_as_such_not_as_an_assertion(repo):
    (repo / "test_new.py").write_text("from calc import missing\n\ndef test_x():\n    assert missing() == 1\n")
    ev = out(tdd(repo, "unit", "red"))
    assert [r["outcome"] for r in ev["runs"]] == ["import-error"]


def test_unit_red_reports_a_syntax_error_as_a_compile_error(repo):
    (repo / "test_new.py").write_text("def test_x(:\n    pass\n")
    ev = out(tdd(repo, "unit", "red"))
    assert [r["outcome"] for r in ev["runs"]] == ["compile-error"]


def test_unit_red_reports_a_passing_new_test_as_pass(repo):
    (repo / "test_new.py").write_text("from calc import add\n\ndef test_ok():\n    assert add(1, 2) == 3\n")
    assert [r["outcome"] for r in out(tdd(repo, "unit", "red"))["runs"]] == ["pass"]


def test_unit_red_with_no_new_test_records_no_run(repo):
    assert out(tdd(repo, "unit", "red"))["runs"] == []


def test_unit_red_reports_a_hanging_test_as_a_timeout(repo):
    (repo / "test_new.py").write_text("import time\n\ndef test_slow():\n    time.sleep(30)\n")
    ev = out(tdd(repo, "unit", "red", TDD_TIMEOUT="2"))
    assert [r["outcome"] for r in ev["runs"]] == ["timeout"]


def test_unit_green_counts_the_suite_and_lists_edited_tests(repo):
    ev = out(tdd(repo, "unit", "green"))
    assert ev["suite"] == {"passed": 1, "failed": 0} and ev["tests_edited"] == []
    (repo / "test_old.py").write_text("def test_old():\n    assert True\n")
    ev = out(tdd(repo, "unit", "green"))
    assert ev["tests_edited"] == ["test_old.py"]


def test_unit_green_counts_a_failing_test(repo):
    (repo / "test_new.py").write_text("def test_f():\n    assert False\n")
    assert out(tdd(repo, "unit", "green"))["suite"] == {"passed": 1, "failed": 1}


def test_unit_refactor_has_the_green_shape(repo):
    assert set(out(tdd(repo, "unit", "refactor"))) >= {"suite", "tests_edited"}


def test_acceptance_green_carries_the_suite_size_recorded_at_red(repo):
    (repo / "test_acc.py").write_text("def test_a():\n    assert False\n")
    red = out(tdd(repo, "acceptance", "red"))
    assert [r["outcome"] for r in red["runs"]] == ["assertion"]
    (repo / "test_acc.py").write_text("def test_a():\n    assert True\n")
    ev = out(tdd(repo, "acceptance", "green"))
    assert ev["expected_count"] == 2 and ev["suite"] == {"passed": 2, "failed": 0}


def test_acceptance_green_without_a_recorded_red_has_no_expected_count(repo):
    assert out(tdd(repo, "acceptance", "green"))["expected_count"] is None


def faults(repo, doc):
    (repo / ".org").mkdir(exist_ok=True)
    (repo / ".org" / "faults.json").write_text(json.dumps(doc))


def test_layer_fault_comes_from_the_declaration_not_from_the_output(repo):
    (repo / "test_l.py").write_text("def test_unit_gap():\n    assert False\n\ndef test_iface():\n    assert False\n")
    faults(repo, {"layer": {"test_l.py::test_unit_gap": "unit", "test_l.py::test_iface": "design"}})
    ev = out(tdd(repo, "layer", "run"))
    assert ev["suite"] == {"passed": 0, "failed": 2} and ev["layer_fault"] == "design"
    faults(repo, {"layer": {"test_l.py::test_unit_gap": "unit", "test_l.py::test_iface": "unit"}})
    assert out(tdd(repo, "layer", "run"))["layer_fault"] == "unit"


def test_layer_all_green_is_no_fault(repo):
    faults(repo, {"layer": {"test_old.py": "unit"}})
    ev = out(tdd(repo, "layer", "run"))
    assert ev["layer_fault"] == "none" and ev["suite"] == {"passed": 1, "failed": 0}


def test_system_fault_is_the_widest_declared_and_undeclared_fails_closed(repo):
    (repo / "test_s.py").write_text("def test_a():\n    assert False\n\ndef test_b():\n    assert False\n")
    faults(repo, {"system": {"test_s.py::test_a": "design", "test_s.py::test_b": "spec"}})
    assert out(tdd(repo, "system", "run"))["system_fault"] == "spec"
    faults(repo, {"system": {"test_s.py::test_a": "design", "test_s.py": "design"}})
    assert out(tdd(repo, "system", "run"))["system_fault"] == "design"
    faults(repo, {"system": {"test_old.py": "design", "test_s.py::test_a": "design"}})
    assert out(tdd(repo, "system", "run"))["system_fault"] == "spec"  # test_b is not declared


def test_system_without_a_declaration_runs_nothing_and_blames_the_spec(repo):
    ev = out(tdd(repo, "system", "run"))
    assert ev["suite"] == {"passed": 0, "failed": 0} and ev["system_fault"] == "spec"


def test_feasibility_reads_the_design_claim_and_fails_closed_on_junk(repo):
    ok = {"feasibility": {"interfaces": True, "modularity": True, "testability": True, "reasons": ["ok"]}}
    assert out(tdd(repo, "feasibility", "check", stdin=json.dumps(ok)))["feasible"] is True
    bad = {"feasibility": {"interfaces": True, "modularity": False, "testability": True, "reasons": ["two modules share state"]}}
    ev = out(tdd(repo, "feasibility", "check", stdin=json.dumps(bad)))
    assert ev["feasible"] is False and ev["failed"] == ["modularity"]
    for junk in ("", "not json", "[]", json.dumps({"feasibility": {"interfaces": True}})):
        assert out(tdd(repo, "feasibility", "check", stdin=junk))["feasible"] is False


def test_deploy_verify_runs_the_configured_command_and_fails_closed(repo):
    cmd = json.dumps([sys.executable, "-c", "import sys; sys.exit(0)"])
    assert out(tdd(repo, "deploy", "verify", TDD_VERIFY_CMD=cmd))["verified"] is True
    cmd = json.dumps([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert out(tdd(repo, "deploy", "verify", TDD_VERIFY_CMD=cmd))["verified"] is False
    assert out(tdd(repo, "deploy", "verify"))["verified"] is False


def test_bug_red_needs_the_failing_test_committed(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "test_bug.py").write_text("from calc import add\n\ndef test_bug():\n    assert add(2, 2) == 5\n")
    ev = out(tdd(repo, "bug", "red", TDD_BASE=base))
    assert ev["committed"] is False and ev["uncommitted"] == ["test_bug.py"]  # only in the working tree
    git(repo, "add", "test_bug.py")
    git(repo, "commit", "-q", "-m", "test: reproduce")
    ev = out(tdd(repo, "bug", "red", TDD_BASE=base))
    assert ev["committed"] is True and ev["uncommitted"] == []
    assert ev["runs"] == [{"test": "test_bug.py::test_bug", "outcome": "assertion"}]
    assert ev["head"] == git(repo, "rev-parse", "HEAD")


def test_bug_red_that_passes_is_reported_as_pass(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "test_bug.py").write_text("def test_bug():\n    assert True\n")
    git(repo, "add", "test_bug.py")
    git(repo, "commit", "-q", "-m", "test")
    ev = out(tdd(repo, "bug", "red", TDD_BASE=base))
    assert [r["outcome"] for r in ev["runs"]] == ["pass"]


def test_unknown_scope_or_phase_exits_two():
    cp = subprocess.run([sys.executable, str(TDD), "unit", "nope"], capture_output=True, text=True)
    assert cp.returncode == 2 and "usage" in cp.stderr


def test_missing_worktree_exits_two(tmp_path):
    cp = subprocess.run([sys.executable, str(TDD), "unit", "green"], capture_output=True, text=True, cwd=tmp_path,
                        env={"PATH": os.environ["PATH"]})
    assert cp.returncode == 2


# ---------------------------------------------------------------- real checks on the real evidence


def run_check(name, key, rel, stdout, tmp_path, run_id=RID):
    ev = tmp_path / f"{name}.json"
    ev.write_text(json.dumps({"run": run_id, "key": key, "steps": {rel: {"exit": 0, "stdout": stdout}}}))
    env = {"PATH": os.environ["PATH"], "ORG_EVIDENCE": str(ev), "ORG_KEY": key, "ORG_RUN": run_id}
    return subprocess.run([sys.executable, str(ROOT / "checks" / f"{name}.py"), key], env=env, capture_output=True, text=True)


def test_tdd_evidence_output_satisfies_the_real_green_and_red_checks(repo, tmp_path):
    (repo / "test_new.py").write_text("from calc import add\n\ndef test_neg():\n    assert add(-1, -1) == -3\n")
    red = tdd(repo, "unit", "red").stdout
    assert run_check("new-test-fails-on-an-assertion-not-a-compile-error", "red-evidence", "red-evidence", red,
                     tmp_path).returncode == 0
    green = tdd(repo, "unit", "green").stdout  # the new test still fails: not green
    assert run_check("suite-green-and-no-test-edited", "green-evidence", "green-evidence", green, tmp_path).returncode == 1


def test_acceptance_green_evidence_satisfies_the_real_suite_check(repo, tmp_path):
    (repo / "test_acc.py").write_text("def test_a():\n    assert False\n")
    tdd(repo, "acceptance", "red")
    (repo / "test_acc.py").write_text("def test_a():\n    assert True\n")
    stdout = tdd(repo, "acceptance", "green").stdout
    assert run_check("acceptance-suite-green", "acceptance-run", "acceptance-run", stdout, tmp_path).returncode == 0


# ---------------------------------------------------------------- bin/merge-change


def test_merge_change_fast_forwards_green_work_into_the_branch(repo):
    git(repo, "checkout", "-q", "-b", "change")
    (repo / "test_n.py").write_text("def test_n():\n    assert True\n")
    git(repo, "add", "test_n.py")
    git(repo, "commit", "-q", "-m", "n")
    git(repo, "checkout", "-q", "main")
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_CHANGE_BRANCH": "change"}
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "main"], capture_output=True, text=True, env=env)
    assert cp.returncode == 0, cp.stderr
    ev = json.loads(cp.stdout)
    assert ev["merged"] is True and ev["head"] == git(repo, "rev-parse", "main") == git(repo, "rev-parse", "change")
    assert ev["ci"] == {"state": "green", "head": ev["head"]}


def test_merge_change_resolves_a_policy_name_from_the_environment(repo):
    git(repo, "checkout", "-q", "-b", "change")
    git(repo, "checkout", "-q", "main")
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_CHANGE_BRANCH": "change",
           "POLICY_VCS_DEFAULT_BRANCH": "main"}
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "vcs.default-branch"], capture_output=True, text=True, env=env)
    assert cp.returncode == 0, cp.stderr


def test_merge_change_undoes_the_merge_when_the_suite_is_red(repo):
    git(repo, "checkout", "-q", "-b", "change")
    (repo / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    git(repo, "add", "test_bad.py")
    git(repo, "commit", "-q", "-m", "bad")
    git(repo, "checkout", "-q", "main")
    before = git(repo, "rev-parse", "main")
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_CHANGE_BRANCH": "change"}
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "main"], capture_output=True, text=True, env=env)
    assert cp.returncode == 1
    assert git(repo, "rev-parse", "main") == before and not (repo / "test_bad.py").exists()


def test_merge_change_refuses_when_the_branch_is_not_checked_out(repo):
    git(repo, "checkout", "-q", "-b", "change")
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_CHANGE_BRANCH": "change"}
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "main"], capture_output=True, text=True, env=env)
    assert cp.returncode == 2 and "main" in cp.stderr


def test_merge_change_needs_into_and_a_change_branch(repo):
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo)}
    assert subprocess.run([sys.executable, str(MERGE)], capture_output=True, text=True, env=env).returncode == 2
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "main"], capture_output=True, text=True, env=env)
    assert cp.returncode == 2


def test_merge_change_refuses_a_dirty_worktree(repo):
    git(repo, "branch", "change")
    (repo / "calc.py").write_text("x = 1\n")
    env = {"PATH": os.environ["PATH"], "TDD_WORKTREE": str(repo), "TDD_CHANGE_BRANCH": "change"}
    cp = subprocess.run([sys.executable, str(MERGE), "--into", "main"], capture_output=True, text=True, env=env)
    assert cp.returncode == 2 and "clean" in cp.stderr


def test_bin_programs_are_executable_and_no_longer_stubs():
    for p in (TDD, MERGE):
        assert os.access(p, os.X_OK)
        assert "not implemented" not in p.read_text()


def test_no_local_paths_in_the_new_files():
    bad = ("claude-" + "501", "/Us" + "ers/", "~/Fun/" + "plans", "/private/" + "tmp")
    files = [TDD, MERGE, Path(__file__)] + [ROOT / "workflows" / f"{n}.yaml" for n in NAMES if (ROOT / "workflows" / f"{n}.yaml").exists()]
    for f in files:
        assert not [b for b in bad if b in f.read_text()], f
