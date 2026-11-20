"""Tests for check_change, derived from the org-documents spec section 10 and the K cases of 12.5.

Each test builds a base org root from the validate_org fixtures, edits a copy, and reads the rungs back.
Entries are (path, task path, row, rung); the refused list holds the entries whose rung the proposer may not use.
"""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIX = os.path.join(HERE, "fixtures", "validate_org")
sys.path.insert(0, SCRIPTS)

import check_change as cc  # noqa: E402

ORDER = ["free", "ordinary", "protected", "frozen"]
SW = "workflows/sw-development.json"
TDD = "workflows/tdd-unit.json"
MANIFEST = "manifest.json"
CATALOG = "metrics.json"
IMPROVER = {"free"}


def _fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


def _root():
    files = {
        MANIFEST: _fixture("manifest.json"),
        CATALOG: _fixture("catalog.json"),
        SW: _fixture("sw-development.json"),
        TDD: _fixture("tdd-unit.json"),
        "briefs/review.md": b"review the change\n",
        "briefs/spec.md": b"write the spec\n",
        "criteria/review.md": b"a review is good when\n",
        "criteria/spec.md": b"a spec is good when\n",
        "checks/spec-check.py": b"print('spec')\n",
        "checks/acceptance-suite-green.py": b"print('green')\n",
        "checks/other-check.py": b"print('other')\n",
        "schemas/item.json": b"{}\n",
        "collectors/spec_rework.py": b"# spec-rework\n",
        "collectors/lead_time.py": b"# lead-time\n",
        "collectors/defects_escaped.py": b"# defects-escaped\n",
        "bin/merge-change": b"#!/bin/sh\n",
        "stack.yaml": b"tools: []\n",
    }
    return files


def _load(files, path):
    return json.loads(files[path])


def _put(files, path, doc):
    files[path] = json.dumps(doc, indent=2).encode()


def edit(files, path, fn):
    doc = _load(files, path)
    fn(doc)
    _put(files, path, doc)


def find(doc, name):
    stack = [doc["do"]]
    while stack:
        for item in stack.pop():
            (n, t), = item.items()
            if n == name:
                return t
            if isinstance(t.get("do"), list):
                stack.append(t["do"])
            if isinstance(t.get("try"), list):
                stack.append(t["try"])
            if isinstance(t.get("catch"), dict) and isinstance(t["catch"].get("do"), list):
                stack.append(t["catch"]["do"])
            if isinstance(t.get("fork"), dict):
                stack.append(t["fork"]["branches"])
    raise KeyError(name)


def find_list(doc, name):
    """Return (list holding the task, its index)."""
    stack = [doc["do"]]
    while stack:
        lst = stack.pop()
        for i, item in enumerate(lst):
            (n, t), = item.items()
            if n == name:
                return lst, i
            if isinstance(t.get("do"), list):
                stack.append(t["do"])
    raise KeyError(name)


def org(doc, name):
    return find(doc, name)["metadata"]["org"]


def pair(fn, path=SW):
    base = _root()
    new = dict(base)
    edit(new, path, fn)
    return base, new


def check(base, new, rungs=IMPROVER):
    return cc.check_change(base, new, set(rungs))


def top(entries):
    return max((e[3] for e in entries), key=ORDER.index) if entries else None


def rung(fn, path=SW):
    base, new = pair(fn, path)
    entries, _ = check(base, new)
    return top(entries)


def file_rung(path, content, base=None):
    base = base or _root()
    new = dict(base)
    new[path] = content
    entries, _ = check(base, new)
    return top(entries)


def tasks_with_row(entries, prefix):
    return [e for e in entries if e[2].startswith(prefix)]


# ---------------------------------------------------------------- contract


def test_identical_roots_give_no_entries():
    base = _root()
    assert check(base, dict(base)) == ([], [])


def test_returns_entries_and_refused_list():
    base, new = pair(lambda d: d["do"].append({"extra": {"set": {"x": 1}}}))
    entries, refused = check(base, new)
    assert entries and all(len(e) == 4 for e in entries)
    assert refused == [e for e in entries if e[3] not in IMPROVER]
    assert refused  # protected is not free


def test_rungs_set_decides_what_is_refused():
    base, new = pair(lambda d: d["do"].append({"extra": {"set": {"x": 1}}}))
    _, refused = check(base, new, {"free", "ordinary", "protected"})
    assert refused == []
    _, refused = check(base, new, {"free", "ordinary"})
    assert refused


def test_reformatting_a_workflow_changes_nothing():
    base = _root()
    new = dict(base)
    new[SW] = json.dumps(_load(base, SW), indent=4, sort_keys=True).encode()
    assert check(base, new) == ([], [])


def test_absent_in_both_versions_is_no_change():
    base = _root()
    base["checks/gone.py"] = None
    new = dict(base)
    assert check(base, new) == ([], [])


# ---------------------------------------------------------------- K cases


def test_K1_remove_merge_is_frozen():
    base, new = pair(lambda d: d["do"].remove(next(i for i in d["do"] if "merge" in i)))
    entries, refused = check(base, new)
    assert top(entries) == "frozen"
    assert ("workflows/sw-development.json", "merge") in [(e[0], e[1]) for e in tasks_with_row(entries, "removing a task")]
    assert refused


def test_K2_add_set_task_at_end_is_protected():
    assert rung(lambda d: d["do"].append({"note": {"set": {"x": 1}}})) == "protected"


def test_K3_swap_floors_review_and_merge_gate_is_frozen():
    def swap(d):
        lst, i = find_list(d, "review")
        assert "merge-gate" in lst[i + 1]
        lst[i], lst[i + 1] = lst[i + 1], lst[i]
    base, new = pair(swap)
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert tasks_with_row(entries, "floor position")


def test_K4_swap_merge_and_report_is_protected():
    def swap(d):
        lst, i = find_list(d, "merge")
        assert "report" in lst[i + 1]
        lst[i], lst[i + 1] = lst[i + 1], lst[i]
    base, new = pair(swap)
    entries, _ = check(base, new)
    assert top(entries) == "protected"
    assert tasks_with_row(entries, "reordering tasks")


def test_K5_brief_text_is_free_but_brief_path_is_frozen():
    entries, refused = check(_root(), {**_root(), "briefs/review.md": b"new text\n"})
    assert top(entries) == "free" and refused == []
    assert rung(lambda d: org(d, "review").update(brief="briefs/spec.md")) == "frozen"


def test_K6_catalog_entries_by_exposure():
    def bump(name):
        def fn(c):
            c[name]["formula"] = "changed"
        return fn
    assert rung(bump("defects-escaped"), CATALOG) == "frozen"  # on floor review
    assert rung(bump("spec-rework"), CATALOG) == "frozen"  # targeted
    assert rung(bump("lead-time"), CATALOG) == "protected"


def test_K7_new_catalog_entry_nobody_names_is_ordinary():
    def add(c):
        c["brand-new"] = copy.deepcopy(c["lead-time"])
    assert rung(add, CATALOG) == "ordinary"


@pytest.mark.parametrize("breakage", [
    b"{not json",
    b'{"do": [], "do": []}',  # duplicate key
    b"[1, 2]",  # not a map
    b'{"do": [{"a": {"set": {}}, "b": {"set": {}}}]}',  # a task item with two names
    b'{"do": {"not": "a list"}}',
    b"\xff\xfe",
])
def test_K8_new_workflow_that_does_not_load_is_frozen_and_refused(breakage):
    base, new = pair(lambda d: None)
    new[SW] = breakage
    entries, refused = check(base, new)
    assert top(entries) == "frozen"
    assert any(e[0] == SW and e[3] == "frozen" for e in refused)


def test_K8_base_that_does_not_load_is_frozen_too():
    base, new = pair(lambda d: None)
    base[SW] = b"{not json"
    entries, refused = check(base, new)
    assert top(entries) == "frozen" and refused


def test_K9_rename_align_is_frozen():
    def rename(d):
        lst, i = find_list(d, "align")
        (n, t), = lst[i].items()
        lst[i] = {"align-goal": t}
    base, new = pair(rename)
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert any(e[1] == "align" and e[3] == "frozen" for e in entries)
    assert any(e[1] == "align-goal" for e in entries)


def test_K10_insert_set_before_review_is_protected():
    def insert(d):
        lst, i = find_list(d, "review")
        lst.insert(i, {"note": {"set": {"x": 1}}})
    base, new = pair(insert)
    entries, _ = check(base, new)
    assert top(entries) == "protected"
    assert not tasks_with_row(entries, "floor")


def _rework(d):
    lst, i = find_list(d, "spec")
    spec = lst.pop(i)
    lst.insert(i, {"rework": {"for": {"each": "round", "in": [1, 2]},
                              "while": "${ $accepted[\"rework/spec\"] != true }", "do": [spec]}})


def test_K11_set_inside_rework_loop_with_floor_is_frozen():
    base = _root()
    edit(base, SW, _rework)
    new = dict(base)
    edit(new, SW, lambda d: find(d, "rework")["do"].append({"note": {"set": {"x": 1}}}))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert any(e[1] == "rework" and e[2].startswith("floor") for e in entries)


def test_K12_adding_sample_to_a_rubric_item_is_frozen():
    base = _root()
    new = dict(base)
    edit(new, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.5))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert tasks_with_row(entries, "weakening an acceptance item")


def test_K13_edit_check_named_by_floor_is_frozen():
    assert file_rung("checks/spec-check.py", b"changed\n") == "frozen"


def test_K14_edit_check_named_only_by_non_floor_is_protected():
    assert file_rung("checks/acceptance-suite-green.py", b"changed\n") == "protected"


def test_K15_collector_of_targeted_metric_is_frozen_other_is_protected():
    assert file_rung("collectors/spec_rework.py", b"changed\n") == "frozen"
    assert file_rung("collectors/lead_time.py", b"changed\n") == "protected"


def test_K16_call_to_workflow_with_floors_is_a_floor():
    def manifest(m):
        m["workflows"]["tdd-unit"]["floors"] = ["red"]
    base = _root()
    edit(base, MANIFEST, manifest)
    # call target changed
    new = dict(base)
    edit(new, SW, lambda d: find(d, "tdd")["run"]["workflow"].update(name="improve"))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    # tdd removed
    new = dict(base)

    def remove(d):
        lst, i = find_list(d, "tdd")
        lst.pop(i)
    edit(new, SW, remove)
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    # with no floors in the callee, a target change is an ordinary non-floor edit
    plain = _root()
    new = dict(plain)
    edit(new, SW, lambda d: find(d, "tdd")["run"]["workflow"].update(name="improve"))
    entries, _ = check(plain, new)
    assert top(entries) == "protected"


def test_K16_floor_call_status_comes_from_either_manifest_version():
    base = _root()
    new = dict(base)
    edit(new, MANIFEST, lambda m: m["workflows"]["tdd-unit"].update(floors=["red"]))
    edit(new, SW, lambda d: find(d, "tdd")["run"]["workflow"].update(name="improve"))
    entries, _ = check(base, new)
    assert any(e[1] == "build/units/tdd" and e[3] == "frozen" for e in entries)


def test_K17_for_in_length_is_ordinary():
    assert rung(lambda d: find(d, "build")["for"].update({"in": [1, 2, 3]})) == "ordinary"


def test_K18_floor_gate_timeout_is_frozen():
    assert rung(lambda d: find(d, "merge-gate")["timeout"]["after"].update(days=3)) == "frozen"


# ---------------------------------------------------------------- rows of the table, one test each


def test_manifest_any_key_is_frozen():
    assert rung(lambda m: m.update(owner="someone"), MANIFEST) == "frozen"
    assert rung(lambda m: m["roles"]["worker"].update(summary="x"), MANIFEST) == "frozen"


def test_unparsable_manifest_freezes_what_depends_on_it():
    base = _root()
    new = dict(base)
    new[MANIFEST] = b"{broken"
    new["collectors/lead_time.py"] = b"changed\n"
    entries, refused = check(base, new)
    assert top(entries) == "frozen"
    assert any(e[0] == "collectors/lead_time.py" and e[3] == "frozen" for e in entries)


def test_floor_task_any_change_is_frozen():
    assert rung(lambda d: org(d, "spec").update(role="reviewer")) == "frozen"
    assert rung(lambda d: org(d, "spec")["metrics"].append("escalations")) == "frozen"
    assert rung(lambda d: org(d, "spec")["acceptance"].append({"check": "x-check"})) == "frozen"
    assert rung(lambda d: find(d, "spec")["run"]["shell"].update(arguments=["--x"])) == "frozen"
    assert rung(lambda d: find(d, "review").update({"if": "${ true }"})) == "frozen"
    assert rung(lambda d: find(d, "review").update({"then": "end"})) == "frozen"
    assert rung(lambda d: org(d, "review").pop("floor")) == "frozen"  # a floor removed


def test_adding_a_floor_flag_is_frozen():
    assert rung(lambda d: org(d, "merge").update(floor=True)) == "frozen"


def test_adding_a_floor_task_is_frozen():
    def add(d):
        d["do"].append({"extra-floor": {"run": {"shell": {"command": "x", "arguments": []}},
                                        "metadata": {"org": {"floor": True, "by": "code", "role": "ci",
                                                             "metrics": [], "acceptance": []}}}})
    assert rung(add) == "frozen"


def test_removing_a_leaf_with_acceptance_is_frozen():
    def remove(d):
        lst, i = find_list(d, "acceptance-run")
        lst.pop(i)
    assert rung(remove) == "frozen"


def test_removing_a_task_that_carries_nothing_is_protected():
    def remove(d):
        lst, i = find_list(d, "not-accepted")
        lst.pop(i)
    assert rung(remove) == "protected"


def test_removal_of_acceptance_or_metrics_is_frozen_whatever_else_changes():
    for key in ("acceptance", "metrics"):
        def drop(d, key=key):
            org(d, "report").pop(key)
        base, new = pair(drop)
        entries, refused = check(base, new, {"free", "ordinary", "protected"})
        assert top(entries) == "frozen" and refused, key
    # combined with a free-rung edit it is still refused
    base, new = pair(lambda d: org(d, "report").pop("acceptance"))
    new["briefs/review.md"] = b"new text\n"
    entries, refused = check(base, new)
    assert {e[3] for e in entries} == {"free", "frozen"}
    assert refused and all(e[3] == "frozen" for e in refused)


def test_removing_one_metrics_entry_or_acceptance_item_is_frozen():
    assert rung(lambda d: org(d, "merge").update(metrics=[])) == "frozen"
    assert rung(lambda d: org(d, "acceptance-tests")["acceptance"].pop(0)) == "frozen"


def test_replacing_a_metric_is_removal_plus_addition():
    base, new = pair(lambda d: org(d, "merge").update(metrics=["escalations"]))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert tasks_with_row(entries, "adding a metric")


@pytest.mark.parametrize("edit_item", [
    lambda item: item.update(rubric="criteria/other.md"),
    lambda item: item.update(judge="owner"),
])
def test_weakening_a_rubric_item_is_frozen(edit_item):
    assert rung(lambda d: edit_item(org(d, "align")["acceptance"][0])) == "frozen"


def test_weakening_check_name_is_frozen():
    assert rung(lambda d: org(d, "merge")["acceptance"][0].update(check="always-true")) == "frozen"


def test_weakening_human_text_is_frozen():
    base = _root()
    edit(base, SW, lambda d: org(d, "merge-gate").pop("floor"))
    new = dict(base)
    edit(new, SW, lambda d: org(d, "merge-gate")["acceptance"][0].update(human="anything goes"))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"
    assert tasks_with_row(entries, "weakening an acceptance item")


def test_changing_acceptance_item_order_is_not_a_removal():
    def reorder(d):
        org(d, "acceptance-tests")["acceptance"].reverse()
    entries, _ = check(*pair(reorder))
    assert top(entries) == "protected"  # indices name rubric verdicts, so an order change is not free


def test_criteria_content_is_frozen():
    assert file_rung("criteria/review.md", b"easier\n") == "frozen"


def test_catalog_entry_removal_by_exposure():
    def drop(name):
        return lambda c: c.pop(name)
    assert rung(drop("defects-escaped"), CATALOG) == "frozen"
    assert rung(drop("acceptance-coverage"), CATALOG) == "frozen"  # targeted
    assert rung(drop("lead-time"), CATALOG) == "protected"


def test_check_script_named_by_floor_via_floor_call_is_frozen():
    base = _root()
    edit(base, MANIFEST, lambda m: m["workflows"]["tdd-unit"].update(floors=["red"]))
    new = dict(base)
    new["checks/other-check.py"] = b"changed\n"
    # not named by anything: protected
    assert top(check(base, new)[0]) == "protected"
    # name it from the floor-call task's acceptance in both versions
    edit(base, SW, lambda d: org(d, "tdd")["acceptance"].append({"check": "other-check"}))
    new = dict(base)
    new["checks/other-check.py"] = b"changed\n"
    assert top(check(base, new)[0]) == "frozen"


def test_schema_endpoint_named_by_floor_is_frozen():
    assert file_rung("schemas/item.json", b'{"type": "object"}\n') == "frozen"  # spec's output endpoint


def test_schema_not_named_by_a_floor_is_protected():
    assert file_rung("schemas/unrelated.json", b"{}\n") == "protected"


def test_floor_run_command_script_is_frozen_non_floor_is_protected():
    base = _root()
    edit(base, SW, lambda d: find(d, "review")["run"]["shell"].update(command="review-tool"))
    base["bin/review-tool"] = b"#!/bin/sh\n"
    assert file_rung("bin/review-tool", b"#!/bin/sh\necho x\n", base) == "frozen"
    assert file_rung("bin/merge-change", b"#!/bin/sh\necho x\n") == "protected"  # merge is not a floor


def test_collector_of_floor_listed_metric_is_frozen():
    assert file_rung("collectors/defects_escaped.py", b"changed\n") == "frozen"


def test_adding_a_non_floor_task_is_protected_nested():
    assert rung(lambda d: find(d, "build")["do"].append({"note": {"set": {"x": 1}}})) == "protected"


def test_reorder_with_no_floor_index_change_is_protected():
    def swap(d):
        lst = find(d, "build")["do"]
        lst[0], lst[1] = lst[1], lst[0]
    entries, _ = check(*pair(swap))
    assert top(entries) == "protected"


@pytest.mark.parametrize("fn", [
    lambda d: org(d, "merge").update(by="human"),
    lambda d: org(d, "merge").update(role="lead"),
    lambda d: org(d, "align").update(brief="briefs/spec.md"),
    lambda d: find(d, "merge")["run"]["shell"].update(arguments=["--into", "elsewhere"]),
    lambda d: find(d, "merge")["run"]["shell"].update(command="other-command"),
    lambda d: find(d, "not-accepted")["metadata"]["org"].update(to="owner"),
    lambda d: d["document"]["metadata"]["org"].update(policy=["work.tracker"]),
], ids=["by", "role", "brief-path", "arguments", "command", "to", "doc-policy"])
def test_protected_key_changes_on_non_floor(fn):
    assert rung(fn) == "protected"


def test_adding_a_metric_or_acceptance_item_is_protected():
    assert rung(lambda d: org(d, "merge")["metrics"].append("escalations")) == "protected"
    assert rung(lambda d: org(d, "merge")["acceptance"].append({"check": "extra"})) == "protected"


def test_raising_a_sample_is_protected():
    base = _root()
    edit(base, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.5))
    new = dict(base)
    edit(new, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.8))
    entries, _ = check(base, new)
    assert top(entries) == "protected"
    # raising to the default (removing sample) is a raise as well
    new = dict(base)
    edit(new, TDD, lambda d: org(d, "unit-review")["acceptance"][0].pop("sample"))
    assert top(check(base, new)[0]) == "protected"


def test_lowering_a_sample_is_frozen():
    base = _root()
    edit(base, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.8))
    new = dict(base)
    edit(new, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.2))
    assert top(check(base, new)[0]) == "frozen"


def test_a_sample_that_is_not_a_number_fails_closed():
    base = _root()
    edit(base, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample=0.5))
    new = dict(base)
    edit(new, TDD, lambda d: org(d, "unit-review")["acceptance"][0].update(sample="all"))
    assert top(check(base, new)[0]) == "frozen"


@pytest.mark.parametrize("fn", [
    lambda d: find(d, "merge").update({"if": "${ true }"}),
    lambda d: find(d, "merge").pop("if"),
    lambda d: find(d, "build").update({"while": "${ false }"}),
    lambda d: find(d, "merge").update({"then": "end"}),
], ids=["if-changed", "if-removed", "while", "then-added"])
def test_flow_changes_on_non_floor_are_protected(fn):
    assert rung(fn) == "protected"


def test_switch_case_on_non_floor_is_protected():
    base = _root()
    edit(base, SW, lambda d: d["do"].append(
        {"route": {"switch": [{"a": {"when": "${ true }", "then": "end"}}]}}))
    new = dict(base)
    edit(new, SW, lambda d: find(d, "route")["switch"][0]["a"].update(when="${ false }"))
    assert top(check(base, new)[0]) == "protected"


def test_retry_count_and_timeout_on_non_floor_are_ordinary():
    base = _root()
    edit(base, SW, lambda d: d["do"].append(
        {"flaky": {"try": [{"inner": {"set": {"x": 1}}}],
                   "catch": {"retry": {"limit": {"attempt": {"count": 3}}}, "do": []}}}))
    new = dict(base)
    edit(new, SW, lambda d: find(d, "flaky")["catch"]["retry"]["limit"]["attempt"].update(count=5))
    assert top(check(base, new)[0]) == "ordinary"
    new = dict(_root())
    edit(new, SW, lambda d: find(d, "acceptance-run").update(timeout={"after": {"minutes": 5}}))
    assert top(check(_root(), new)[0]) == "ordinary"


def test_retry_delay_is_not_a_listed_bound():
    base = _root()
    edit(base, SW, lambda d: d["do"].append(
        {"flaky": {"try": [{"inner": {"set": {"x": 1}}}],
                   "catch": {"retry": {"delay": {"seconds": 1}, "limit": {"attempt": {"count": 3}}}, "do": []}}}))
    new = dict(base)
    edit(new, SW, lambda d: find(d, "flaky")["catch"]["retry"].update(delay={"seconds": 99}))
    assert top(check(base, new)[0]) == "protected"


def test_for_in_replaced_values_is_not_a_bound_change():
    assert rung(lambda d: find(d, "build")["for"].update({"in": ["a", "b"]})) == "protected"
    assert rung(lambda d: find(d, "build")["for"].update({"in": "${ .rounds }"})) == "protected"


def test_for_in_shrinking_is_ordinary_too():
    assert rung(lambda d: find(d, "build")["for"].update({"in": [1]})) == "ordinary"


def test_new_catalog_entry_named_by_a_workflow_is_protected_not_ordinary():
    base = _root()
    edit(base, CATALOG, lambda c: c.pop("lead-time"))
    # `merge` names lead-time in both versions, so re-adding it is not "unnamed"
    new = dict(base)
    edit(new, CATALOG, lambda c: c.update({"lead-time": {"scope": "node"}}))
    assert top(check(base, new)[0]) == "protected"


def test_new_catalog_entry_that_is_floor_listed_is_frozen():
    base = _root()
    edit(base, CATALOG, lambda c: c.pop("escalations"))
    new = dict(base)
    edit(new, CATALOG, lambda c: c.update({"escalations": {"scope": "process"}}))
    assert top(check(base, new)[0]) == "frozen"


def test_other_files_under_the_org_root_are_protected():
    assert file_rung("docs/notes.txt", b"hello\n") == "protected"
    assert file_rung("checks/other-check.py", b"changed\n") == "protected"
    assert file_rung("collectors/new_collector.py", b"x\n") == "protected"
    assert file_rung("briefs/odd.txt", b"x\n") == "protected"  # briefs/*.md only


def test_new_and_removed_briefs_are_free():
    assert file_rung("briefs/new.md", b"hello\n") == "free"
    base = _root()
    new = dict(base)
    new["briefs/review.md"] = None
    assert top(check(base, new)[0]) == "free"


def test_stack_document_is_free():
    entries, refused = check(_root(), {**_root(), "stack.yaml": b"tools: [x]\n"})
    assert top(entries) == "free" and refused == []


def test_path_outside_the_org_root_fails_closed():
    assert file_rung("../escape.md", b"x\n") == "frozen"
    assert file_rung("/abs/path.md", b"x\n") == "frozen"
    assert file_rung("briefs/../criteria/review.md", b"x\n") == "frozen"


# ---------------------------------------------------------------- combined and adversarial


def test_combined_change_takes_the_highest_rung():
    base, new = pair(lambda d: (find(d, "build")["for"].update({"in": [1, 2, 3]}),
                                d["do"].append({"note": {"set": {"x": 1}}})))
    new["briefs/review.md"] = b"edited\n"
    entries, refused = check(base, new, {"free", "ordinary"})
    assert {e[3] for e in entries} == {"free", "ordinary", "protected"}
    assert top(entries) == "protected"
    assert refused and all(e[3] == "protected" for e in refused)
    # add a frozen change: the top moves up
    edit(new, SW, lambda d: org(d, "spec").update(role="worker"))
    entries, _ = check(base, new)
    assert top(entries) == "frozen"


def test_a_floor_criteria_target_or_grammar_style_edit_is_refused_for_the_improver():
    for path, content in (("criteria/spec.md", b"weaker\n"), (MANIFEST, b"{}"), ("checks/spec-check.py", b"pass\n")):
        base = _root()
        new = dict(base)
        new[path] = content
        _, refused = check(base, new)
        assert refused and refused[0][3] == "frozen", path


def test_target_removal_in_manifest_is_refused():
    assert rung(lambda m: m["targets"].pop("spec-rework"), MANIFEST) == "frozen"


def test_hidden_children_of_a_task_that_cannot_be_walked_fail_closed():
    # `do` and `try` together make the kind undefined, so validate_org never walks the children
    base = _root()
    edit(base, SW, lambda d: d["do"].append(
        {"odd": {"do": [{"a": {"set": {"x": 1}}}], "try": [{"b": {"set": {"x": 1}}}]}}))
    new = dict(base)
    edit(new, SW, lambda d: find(d, "odd")["do"][0]["a"]["set"].update(x=2))
    assert top(check(base, new)[0]) == "frozen"


def test_duplicate_task_paths_fail_closed():
    base = _root()
    new = dict(base)
    edit(new, SW, lambda d: d["do"].append(copy.deepcopy(d["do"][0])))  # a second `align`
    assert top(check(base, new)[0]) == "frozen"


def test_one_and_true_are_different_values():
    base = _root()
    edit(base, SW, lambda d: find(d, "build")["for"].update({"in": [1, 2]}))
    new = dict(base)
    edit(new, SW, lambda d: find(d, "build")["for"].update({"in": [True, 2]}))
    assert top(check(base, new)[0]) == "protected"  # a change, not an equality


def test_nested_non_floor_edits_use_the_full_task_path():
    base, new = pair(lambda d: org(d, "acceptance-run").update(role="lead"))
    entries, _ = check(base, new)
    assert [(e[1], e[3]) for e in entries] == [("build/acceptance-run", "protected")]


def test_added_workflow_file_with_a_floor_is_frozen():
    base = _root()
    new = dict(base)
    wf = _load(base, TDD)
    wf["document"]["name"] = "tdd-two"
    org(wf, "red")["floor"] = True
    _put(new, "workflows/tdd-two.json", wf)
    assert top(check(base, new)[0]) == "frozen"


def test_removed_workflow_file_is_frozen():
    base = _root()
    new = dict(base)
    new[TDD] = None
    assert top(check(base, new)[0]) == "frozen"


def test_unreadable_catalog_fails_closed():
    base, new = pair(lambda c: None, CATALOG)
    new[CATALOG] = b"[not, a, map]"
    entries, refused = check(base, new)
    assert top(entries) == "frozen" and refused


def test_yaml_workflow_loads_with_pyyaml():
    pytest.importorskip("yaml")
    base = _root()
    base["workflows/extra.yaml"] = b"document:\n  name: extra\ndo: []\n"
    new = dict(base)
    new["workflows/extra.yaml"] = b"document:\n  name: extra\ndo:\n  - note:\n      set:\n        x: 1\n"
    entries, _ = check(base, new)
    assert top(entries) == "protected"
    new["workflows/extra.yaml"] = b"document: [unclosed\n"
    assert top(check(base, new)[0]) == "frozen"
