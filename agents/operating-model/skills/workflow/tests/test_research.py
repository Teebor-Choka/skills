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

# What the research workflow adds to the manifest. A real deploy needs an owner-signed manifest change.
RESEARCH_ROLES = {"researcher": {"escalates-to": "lead", "summary": "frames questions, searches, drafts notes"}}
RESEARCH_FLOORS = ["cite-check", "claim-review"]
CITE_CHECK = "every-claim-cites-a-source"


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _manifest():
    m = _json(os.path.join(FIX, "manifest.json"))
    m["roles"].update(copy.deepcopy(RESEARCH_ROLES))
    m["roles"]["lead"]["may-spawn"].append("researcher")
    m["workflows"]["research"] = {"path": "workflows/research.yaml", "floors": list(RESEARCH_FLOORS)}
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
    assert vm.validate_manifest(m, cat, str(root)) == []


# --- acceptance items 2 and 3: constructs, claim review with a rubric, a code check for citations ---


def test_research_contract_is_met(flow):
    assert contract_errors(flow) == []


def test_uses_switch_and_fork_and_a_counted_listen_any(flow):
    keys = {k for _, _, t in tasks(flow) for k in ("switch", "fork", "wait", "listen") if k in t}
    assert {"switch", "fork", "listen"} <= keys
    join = find(flow, "claims-checked")
    assert "any" in join["listen"]["to"] and "until" in join["listen"]["to"]


def test_join_is_skipped_when_there_are_no_claims(flow):
    # With zero claims no event arrives, `until` is never evaluated, and the join would time out.
    cond = find(flow, "claims-checked").get("if")
    assert cond, "claims-checked has no if guard for an empty claim list"
    assert expr.evaluate(expr.unwrap(cond), None, {"context": {"claims": []}}) is False
    assert expr.evaluate(expr.unwrap(cond), None, {"context": {"claims": [{"id": "c1"}]}}) is True


def test_claim_review_and_cite_check_are_floors(flow):
    for name in RESEARCH_FLOORS:
        assert find(flow, name)["metadata"]["org"].get("floor") is True
    assert find(flow, "cite-check")["metadata"]["org"]["acceptance"] == [{"check": CITE_CHECK}]


def test_check_items_sit_only_on_code_tasks(flow):
    # Spec 6.1: a check reads evidence built only from `by: code` step results, never agent output,
    # so a check on a model task could not see what that task produced.
    for path, _, t in tasks(flow):
        o = t.get("metadata", {}).get("org", {})
        if any("check" in i for i in o.get("acceptance", [])):
            assert o.get("by") == "code", f"{path}: check item on a by: {o.get('by')} task"


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
