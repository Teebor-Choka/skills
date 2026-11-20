"""Acceptance tests for the research workflow (unit U4): a question in, a cited, claim-reviewed note out.

The workflow is written against the org-documents spec and checked with the shipped validators.
The real manifest and metrics.json belong to another unit, so the tests extend the validate_org
fixtures with the research entry the workflow needs (see RESEARCH_ROLES and RESEARCH_FLOORS).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(HERE)
SCRIPTS = os.path.join(W, "scripts")
FIX = os.path.join(HERE, "fixtures", "validate_org")
FLOW = os.path.join(W, "workflows", "research.yaml")
CATALOG = os.path.join(W, "metrics.research.json")
sys.path.insert(0, SCRIPTS)

import expr  # noqa: E402
import validate_catalog as vc  # noqa: E402
import validate_manifest as vm  # noqa: E402
import validate_org as vo  # noqa: E402

try:
    import interpreter as it  # U13a; absent on bases older than wave 3
except ImportError:
    it = None

# What the research workflow adds to the manifest. A real deploy needs an owner-signed manifest change.
RESEARCH_ROLES = {
    "researcher": {"escalates-to": "lead", "summary": "frames questions, searches, drafts notes"},
    "requester": {"escalates-to": "lead", "summary": "asked the question; accepts the note (signer, P18)"},
}
RESEARCH_FLOORS = ["cite-check", "claim-review"]
CITE_CHECK = "every-claim-cites-a-source"
# Spec 6.1 classes (P25). A fact check reads the producing code step's own result; a shape check reads output.
RESEARCH_CHECKS = {
    CITE_CHECK: "fact",  # on claim-cites steps: their own stdout lists each claim's citation
    "sources-recorded": "fact",  # on prior-notes: notes-search's own stdout
    "note-published": "fact",  # on publish: note-publish's own stdout
    "every-claim-has-a-verdict": "shape",  # on the join: verdicts are agent output, read from outputs
}
SEARCH_STEPS = ["web-search", "literature-search", "lookup", "check-claim"]
NETWORK = "research.source-allowlist"


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _manifest():
    m = _json(os.path.join(FIX, "manifest.json"))
    m["roles"].update(copy.deepcopy(RESEARCH_ROLES))
    m["roles"]["lead"]["may-spawn"].append("researcher")
    m["workflows"]["research"] = {"path": "workflows/research.yaml", "floors": list(RESEARCH_FLOORS)}
    m.setdefault("checks", {}).update(RESEARCH_CHECKS)
    return m


def _catalog():
    files = [("catalog.json", _json(os.path.join(FIX, "catalog.json"))), ("metrics.research.json", _json(CATALOG))]
    merged, errs = vc.merge_catalogs(files)
    assert errs == []
    return merged


@pytest.fixture(scope="module")
def flow():
    pytest.importorskip("yaml", reason="research.yaml is YAML; run with uv run --with pyyaml")
    return vc.load_document(FLOW)


def tasks(doc):
    """(path, name, task) for every task in every nested task list, in pre-order."""
    out = []

    def walk(lst, prefix):
        for item in lst:
            ((name, task),) = item.items()
            out.append((prefix + name, name, task))
            for child in vo._child_lists(task):
                walk(child, prefix + name + "/")

    walk(doc.get("do", []), "")
    return out


def find(doc, name):
    for _, n, t in tasks(doc):
        if n == name:
            return t
    raise AssertionError(f"no task named {name!r}")


def expressions(value):
    """Every `${ }` string anywhere in the document."""
    stack, out = [value], []
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
        elif expr.is_expression(v):
            out.append(v)
    return out


def contract_errors(doc):
    """The research-specific contract (acceptance items 2 and 3 of the brief). Empty when met."""
    errs = []
    all_tasks = tasks(doc)
    if not any("switch" in t or "fork" in t or "wait" in t for _, _, t in all_tasks):
        errs.append("no switch, fork or wait task")
    if not any(isinstance(t.get("listen"), dict) and "any" in (t["listen"].get("to") or {}) for _, _, t in all_tasks):
        errs.append("no listen.to.any task")
    try:
        review = find(doc, "claim-review")
    except AssertionError:
        return errs + ["no claim-review task"]
    items = review.get("metadata", {}).get("org", {}).get("acceptance", [])
    if not any("rubric" in i and "judge" in i for i in items):
        errs.append("claim-review has no rubric item with a judge")
    if not any(i.get("check") == CITE_CHECK for _, _, t in all_tasks
               for i in t.get("metadata", {}).get("org", {}).get("acceptance", [])):
        errs.append(f"no task carries the check {CITE_CHECK}")
    return errs


# --- acceptance item 1: passes U1 (validate_org) and U1b (schema gate) ---


def test_validate_org_accepts_research(flow):
    assert vo.validate_org(flow, _catalog(), _manifest()) == []


def test_validate_org_cli_accepts_research(tmp_path):
    pytest.importorskip("yaml", reason="research.yaml is YAML; run with uv run --with pyyaml")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps(_manifest()), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "validate_org.py"),
         "--catalog", os.path.join(FIX, "catalog.json"), "--catalog", CATALOG,
         "--manifest", str(man), FLOW],
        capture_output=True, text=True,
    )
    assert (r.returncode, r.stderr) == (0, "")


def test_schema_gate_accepts_research():
    pytest.importorskip("yaml", reason="the schema gate needs PyYAML")
    pytest.importorskip("jsonschema", reason="the schema gate needs jsonschema")
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_flow_schema.py"), FLOW],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith(": OK")


def test_research_catalog_does_not_collide_with_the_sw_catalog():
    # C4: names stay unique across catalog files.
    files = [("catalog.json", _json(os.path.join(FIX, "catalog.json"))), ("metrics.research.json", _json(CATALOG))]
    _, errs = vc.merge_catalogs(files)
    assert errs == []
    assert len(_json(CATALOG)) >= 3


def test_research_catalog_shape(tmp_path):
    # Shape only: collectors/ is outside this unit's write-set, so the root here holds empty stubs.
    cat = _json(CATALOG)
    for entry in cat.values():
        p = tmp_path / entry["collector"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    assert vc.validate_catalog([("metrics.research.json", cat)], str(tmp_path)) == []


def test_validate_manifest_with_research_has_no_start_cycle_or_forgery(tmp_path):
    pytest.importorskip("yaml", reason="research.yaml is YAML; run with uv run --with pyyaml")
    root = tmp_path
    src = os.path.join(HERE, "fixtures", "catalog_manifest", "root", "workflows")
    (root / "workflows").mkdir()
    m = _manifest()
    for name in ("sw-development", "tdd-unit", "improve"):
        shutil.copy(os.path.join(src, f"{name}.json"), root / "workflows" / f"{name}.json")
        m["workflows"][name]["path"] = f"workflows/{name}.json"
    shutil.copy(FLOW, root / "workflows" / "research.yaml")
    cat = _catalog()
    for entry in cat.values():
        p = root / entry["collector"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    # Spec 8.1: every name in manifest.checks has checks/<name>.py. Empty stubs: checks/ is outside the write-set.
    (root / "checks").mkdir()
    for name in m["checks"]:
        (root / "checks" / f"{name}.py").write_text("", encoding="utf-8")
    assert vm.validate_manifest(m, cat, str(root)) == []


# --- acceptance items 2 and 3: constructs, claim review with a rubric, a code check for citations ---


def test_research_contract_is_met(flow):
    assert contract_errors(flow) == []


def test_uses_switch_and_fork_and_a_counted_listen_any(flow):
    keys = {k for _, _, t in tasks(flow) for k in ("switch", "fork", "wait", "listen") if k in t}
    assert {"switch", "fork", "listen"} <= keys
    join = find(flow, "claims-checked")
    assert "any" in join["listen"]["to"] and "until" in join["listen"]["to"]


def test_join_counts_task_ended_events(flow):
    # Spec 7.5 (P11 to P13): the join listens on org.task-ended and counts $events. A counted until is
    # evaluated once before the first event, so zero claims complete at once and no if guard is needed.
    join = find(flow, "claims-checked")
    assert "if" not in join
    assert [f["with"]["type"] for f in join["listen"]["to"]["any"]] == ["org.task-ended"]
    until = expr.unwrap(join["listen"]["to"]["until"])

    def done(events, claims):
        return expr.evaluate(until, None, {"events": events, "context": {"claims": claims}})

    assert done([], []) is True
    assert done([{}], [{"id": "c1"}, {"id": "c2"}]) is False
    assert done([{}, {}], [{"id": "c1"}, {"id": "c2"}]) is True


def test_search_steps_name_their_network_policy(flow):
    # Spec 5 (P19): the runtime passes metadata.org.network to the instance request.
    for name in SEARCH_STEPS:
        assert find(flow, name)["metadata"]["org"].get("network") == NETWORK, name


def test_requester_accepts_the_note_with_its_own_signature(flow):
    # Spec 7.5 (P18): a decision gate signed by the requester's key, not the owner's.
    gate = find(flow, "requester-accepts")
    o = gate["metadata"]["org"]
    assert (o["by"], o["role"], o["signer"]) == ("human", "requester", "requester")
    assert any("human" in i for i in o["acceptance"])
    assert "one" in gate["listen"]["to"]
    names = [n for _, n, _ in tasks(flow)]
    assert names.index("review-loop") < names.index("requester-accepts") < names.index("publish")


def join_verdicts(output):
    """What `every-claim-has-a-verdict` reads: claim id to verdict, from the join's own output entry.

    Spec 6.1: a gate's entry stdout is the JSON list of the events it consumed; P41: each
    `org.task-ended` carries the ended work's entry in `data.output`.
    """
    out = {}
    for event in json.loads(output["stdout"]):
        entry = (event.get("data") or {}).get("output") or {}
        result = json.loads(entry.get("stdout") or "null") or {}
        out[result.get("id")] = result.get("verdict")
    return out


def test_join_verdicts_reads_p41_events():
    def ended(i, verdict):
        entry = {"exit": 0, "stdout": json.dumps({"id": f"c{i}", "verdict": verdict})}
        return {"type": "org.task-ended", "data": {"run": "r", "task": f"verify/check-claim#{i}", "accepted": True,
                                                   "output": entry}}

    output = {"exit": 0, "stdout": json.dumps([ended(0, "verified"), ended(1, "refuted")])}
    assert join_verdicts(output) == {"c0": "verified", "c1": "refuted"}
    # Without P41's data.output the join sees no verdict at all.
    bare = [{"type": "org.task-ended", "data": {"run": "r", "task": "verify/check-claim#0", "accepted": True}}]
    assert join_verdicts({"exit": 0, "stdout": json.dumps(bare)}) == {None: None}


@pytest.mark.xfail(strict=True, reason="P41 (org.task-ended carries output) is not yet in the U13a interpreter")
def test_join_check_sees_every_claim_verdict_in_the_join_output(flow):
    if it is None:
        pytest.skip("the U13a interpreter is not on this base")
    run_id = "a" * 32
    claims = [{"id": f"c{i}", "text": "t", "sources": [{"url": "https://example.org", "accessed": "2026-11-20"}]}
              for i in range(3)]
    verdicts = {"c0": "verified", "c1": "hearsay", "c2": "refuted"}
    seen = {}

    def capture(name, key, evidence):
        seen[key] = evidence
        return True

    host = it.ScriptedHost(
        steps={
            "frame": {"output": {"route": "survey", "questions": ["q"]}},
            "extract": {"output": {"claims": claims}},
            "verify/check-claim": lambda req: it.StepOutcome(
                output={"id": req.input["id"], "verdict": verdicts[req.input["id"]]}),
        },
        checks={"every-claim-has-a-verdict": capture},
        events=[(60, {"id": "e1", "type": "org.research-note-accepted", "signature": "requester",
                      "data": {"run": run_id, "task": "requester-accepts", "decision": "approve"}})],
    )
    res = it.Interpreter({"research": flow}, host, _catalog(), _manifest()).run(
        "research", {"question": "q"}, run_id=run_id)
    assert res.status == "success", res.errors
    assert join_verdicts(seen["claims-checked"]["output"]) == verdicts


def test_claim_review_and_cite_check_are_floors(flow):
    for name in RESEARCH_FLOORS:
        assert find(flow, name)["metadata"]["org"].get("floor") is True
    assert find(flow, "cite-check")["metadata"]["org"]["acceptance"] == [{"check": CITE_CHECK}]


def test_fact_checks_sit_only_on_code_tasks(flow):
    # Spec 6.1 (P25): a fact check reads the producing code step's result; on a model task it would read claims.
    classes = _manifest()["checks"]
    for path, _, t in tasks(flow):
        o = t.get("metadata", {}).get("org", {})
        for item in o.get("acceptance", []):
            if "check" in item:
                assert item["check"] in classes, f"{path}: check {item['check']} not in manifest.checks"
                if classes[item["check"]] == "fact":
                    assert o.get("by") == "code", f"{path}: fact check on a by: {o.get('by')} task"


def test_rework_loop_reads_both_floor_results(flow):
    # Spec 7.4 runtime rule 1: a floor in a rework loop is exempt from the immediate raise only
    # when the loop's while names its key.
    loop = find(flow, "review-loop")
    keys = expr.accepted_keys(expr.unwrap(loop["while"]))
    assert {f"review-loop/{f}" for f in RESEARCH_FLOORS} <= set(keys)


def _drop_rubric(d):
    find(d, "claim-review")["metadata"]["org"]["acceptance"] = [{"check": "x"}]


def _drop_cite_check(d):
    for _, _, t in tasks(d):
        o = t.get("metadata", {}).get("org", {})
        if "acceptance" in o:
            o["acceptance"] = [i for i in o["acceptance"] if i.get("check") != CITE_CHECK] or [{"check": "x"}]


def _join_to_one(d):
    find(d, "claims-checked")["listen"]["to"] = {"one": {"with": {"type": "x"}}}


@pytest.mark.parametrize("mutate,expected", [
    (_drop_rubric, "claim-review has no rubric item with a judge"),
    (_drop_cite_check, f"no task carries the check {CITE_CHECK}"),
    (_join_to_one, "no listen.to.any task"),
])
def test_contract_catches_a_removed_construct(flow, mutate, expected):
    # Adversarial: dropping the rubric, the citation check or the counted join must be caught.
    d = copy.deepcopy(flow)
    mutate(d)
    assert expected in contract_errors(d)


def test_removing_a_floor_is_refused_by_validate_org(flow):
    d = copy.deepcopy(flow)
    del find(d, "claim-review")["metadata"]["org"]["floor"]
    errs = vo.validate_org(d, _catalog(), _manifest())
    assert any(e.startswith("review-loop/claim-review: listed as a floor in the manifest but floor is not true")
               for e in errs)


# --- expressions and references ---


def test_every_expression_is_in_the_u5_subset(flow):
    found = expressions(flow)
    assert found
    for e in found:
        expr.parse(expr.unwrap(e))


def test_every_accepted_key_names_a_task(flow):
    paths = {p for p, _, _ in tasks(flow)}
    for e in expressions(flow):
        for key in expr.accepted_keys(expr.unwrap(e)):
            assert key in paths, f"{e} reads $accepted[{key!r}], which is not a task path"


def test_every_brief_and_rubric_exists_with_numbered_rules(flow):
    briefs, rubrics = set(), set()
    for _, _, t in tasks(flow):
        o = t.get("metadata", {}).get("org", {})
        if "brief" in o:
            briefs.add(o["brief"])
        rubrics.update(i["rubric"] for i in o.get("acceptance", []) if "rubric" in i)
    assert briefs and rubrics
    for rel in briefs | rubrics:
        assert rel.split("/")[1] == "research", rel
        assert os.path.isfile(os.path.join(W, rel)), rel
    for rel in rubrics:
        text = open(os.path.join(W, rel), encoding="utf-8").read()
        assert re.search(r"^1\. ", text, re.M), f"{rel}: no numbered pass rules"
        assert re.search(r"^## On a fail", text, re.M), f"{rel}: does not say what the judge reports on a fail"


def test_metrics_named_by_the_workflow_are_in_the_merged_catalog(flow):
    cat = _catalog()
    research = set(_json(CATALOG))
    used = {m for _, _, t in tasks(flow) for m in t.get("metadata", {}).get("org", {}).get("metrics", [])}
    assert used <= set(cat)
    assert research <= used, f"catalog entries no task names: {sorted(research - used)}"


def test_no_local_paths_in_unit_files():
    files = [FLOW, CATALOG]
    for d in ("briefs/research", "criteria/research"):
        base = os.path.join(W, d)
        files += [os.path.join(base, f) for f in sorted(os.listdir(base))] if os.path.isdir(base) else []
    for path in files:
        text = open(path, encoding="utf-8").read()
        for bad in ("claude-" + "501", "/Users" + "/", "~/Fun" + "/plans", "/private" + "/tmp"):
            assert bad not in text, f"{path} holds {bad}"
