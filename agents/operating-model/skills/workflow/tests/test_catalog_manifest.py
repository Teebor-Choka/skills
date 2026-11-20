"""Tests for the metric catalog and manifest validators (spec sections 2, 8, 9, 12.2 to 12.4).

Each error is matched by prefix, as spec 2.3 rule 2 says. YAML tests skip when PyYAML is missing;
the test that proves the missing-package path always runs.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIXTURE = HERE / "fixtures" / "catalog_manifest" / "root"
sys.path.insert(0, str(SCRIPTS))

import validate_catalog as vc  # noqa: E402
import validate_manifest as vm  # noqa: E402

APPENDIX_A = [
    "escalations", "spec-rework", "acceptance-coverage", "red-for-wrong-reason", "acceptance-rounds",
    "defects-found-in-review", "defects-escaped", "lead-time", "decision-latency", "write-set-collisions",
    "review-rounds", "report-complete", "proposals-accepted", "tests-per-unit", "diff-lines", "green-rounds",
]


def has(errs, prefix):
    return any(e.startswith(prefix) for e in errs)


def shown(errs, prefix):
    return f"expected prefix {prefix!r} in {errs!r}"


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jdump(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


@pytest.fixture
def root(tmp_path):
    dst = tmp_path / "root"
    shutil.copytree(FIXTURE, dst)
    return str(dst)


@pytest.fixture
def catalog(root):
    return jload(os.path.join(root, "metrics.json"))


@pytest.fixture
def manifest(root):
    return jload(os.path.join(root, "manifest.json"))


def check_catalog(root, mutate=None, label="metrics.json"):
    cat = jload(os.path.join(root, "metrics.json"))
    if mutate:
        mutate(cat)
    return vc.validate_catalog([(label, cat)], root)


def check_manifest(root, mutate=None, mutate_catalog=None):
    man = jload(os.path.join(root, "manifest.json"))
    cat = jload(os.path.join(root, "metrics.json"))
    if mutate:
        mutate(man)
    if mutate_catalog:
        mutate_catalog(cat)
    return vm.validate_manifest(man, cat, root)


def set_improve(root, tasks, raw=None):
    """Replace the `improve` workflow file. `raw` is written verbatim (for duplicate keys)."""
    p = os.path.join(root, "workflows", "improve.json")
    if raw is not None:
        Path(p).write_text(raw, encoding="utf-8")
        return
    jdump(p, {"document": {"dsl": "1.1.0", "namespace": "org", "name": "improve", "version": "0.1.0"}, "do": tasks})


# ---------------------------------------------------------------- catalog


def test_fixture_catalog_has_the_16_appendix_a_metrics(root):
    cat = jload(os.path.join(root, "metrics.json"))
    assert sorted(cat) == sorted(APPENDIX_A)
    assert len(cat) == 16


def test_fixture_catalog_validates(root):
    errs = vc.validate_catalog([("metrics.json", jload(os.path.join(root, "metrics.json")))], root)
    assert errs == []


@pytest.mark.parametrize("key", ["scope", "unit", "better", "formula", "collector", "reads"])
def test_missing_key_is_named(root, key):
    errs = check_catalog(root, lambda c: c["lead-time"].pop(key))
    assert has(errs, f"catalog: lead-time.{key}: required"), shown(errs, key)


def test_c1_better_dropped(root):
    errs = check_catalog(root, lambda c: c["lead-time"].pop("better"))
    assert has(errs, "catalog: lead-time.better: required")


@pytest.mark.parametrize("value", ["down", "", None, 1, ["lower"], {"a": 1}, True])
def test_c2_better_outside_the_closed_set(root, value):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("better", value))
    assert has(errs, f"catalog: lead-time.better: {value!r} is not one of context, higher, lower")


@pytest.mark.parametrize("value", ["lower", "higher", "context"])
def test_better_accepts_the_closed_set(root, value):
    assert check_catalog(root, lambda c: c["lead-time"].__setitem__("better", value)) == []


def test_c7_scope_team(root):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("scope", "team"))
    assert has(errs, "catalog: lead-time.scope: 'team' is not one of node, process, stage")


@pytest.mark.parametrize("value", ["node", "stage", "process"])
def test_scope_accepts_the_closed_set(root, value):
    assert check_catalog(root, lambda c: c["lead-time"].__setitem__("scope", value)) == []


def test_c3_missing_collector_file(root):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/nope.py"))
    assert has(errs, "catalog: lead-time.collector: file not found under root: collectors/nope.py")


def test_collector_that_is_a_directory_is_not_a_file(root):
    os.makedirs(os.path.join(root, "collectors", "dir.py"))
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/dir.py"))
    assert has(errs, "catalog: lead-time.collector: file not found under root: collectors/dir.py")


def test_collector_symlink_leaving_the_root_is_refused(root, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("# outside\n")
    os.symlink(outside, os.path.join(root, "collectors", "link.py"))
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/link.py"))
    assert has(errs, "catalog: lead-time.collector: file not found under root: collectors/link.py")


def test_collector_symlink_inside_the_root_is_allowed(root):
    os.symlink(os.path.join(root, "collectors", "lead_time.py"), os.path.join(root, "collectors", "alias.py"))
    assert check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/alias.py")) == []


@pytest.mark.parametrize("path", [
    "/etc/x.py", "collectors/../metrics.py", "collectors/./a.py", "collectors//a.py", "collectors\\a.py",
    "collectors/a.txt", "other/a.py", "collectors/.py", "collectors/", "collectors/a.py/", 5, None, ["x"],
    "collectors/a\x00.py", "collectors/a\x1f.py", "collectors/a\x7f.py",
])
def test_collector_path_form(root, path):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", path))
    assert has(errs, "catalog: lead-time.collector: must be a relative path under collectors/ ending .py"), errs


def test_c8_nul_in_collector_does_not_raise(root):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/a\x00.py"))
    assert has(errs, "catalog: lead-time.collector: must be a relative path under collectors/ ending .py")


def test_collector_in_a_subdirectory_is_valid(root):
    os.makedirs(os.path.join(root, "collectors", "sub"))
    shutil.copy(os.path.join(root, "collectors", "lead_time.py"), os.path.join(root, "collectors", "sub", "x.py"))
    assert check_catalog(root, lambda c: c["lead-time"].__setitem__("collector", "collectors/sub/x.py")) == []


def test_c5_name_must_be_kebab_case(root):
    errs = check_catalog(root, lambda c: c.__setitem__("Lead_Time", copy.deepcopy(c["lead-time"])))
    assert has(errs, "catalog: Lead_Time: name must be kebab-case")


@pytest.mark.parametrize("name", ["Lead", "lead_time", "-lead", "lead-", "lead--time", "lead time", "", "lead.time"])
def test_names_that_are_not_kebab_case(root, name):
    errs = check_catalog(root, lambda c: c.__setitem__(name, copy.deepcopy(c["lead-time"])))
    assert has(errs, f"catalog: {name}: name must be kebab-case")


def test_c6_unknown_key(root):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("owner", "x"))
    assert has(errs, "catalog: lead-time: unknown key 'owner'")


@pytest.mark.parametrize("key", ["unit", "formula"])
@pytest.mark.parametrize("value", ["", "   ", None, 3, ["x"]])
def test_unit_and_formula_are_non_empty_strings(root, key, value):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__(key, value))
    assert has(errs, f"catalog: lead-time.{key}: must be a non-empty string")


@pytest.mark.parametrize("value", [[], "run-ledger", None, [1], [""], ["Bad Name"], ["-x"], [["a"]], {"a": 1}])
def test_reads_must_be_a_non_empty_list_of_source_names(root, value):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("reads", value))
    assert has(errs, "catalog: lead-time.reads: must be a non-empty list of source names")


def test_reads_rejects_duplicates(root):
    errs = check_catalog(root, lambda c: c["lead-time"].__setitem__("reads", ["a", "b", "a"]))
    assert has(errs, "catalog: lead-time.reads: duplicate source")


@pytest.mark.parametrize("source", ["run-ledger", "item.json", "test_ids", "a1", "x.y-z"])
def test_reads_accepts_source_names(root, source):
    assert check_catalog(root, lambda c: c["lead-time"].__setitem__("reads", [source])) == []


@pytest.mark.parametrize("entry", [None, 1, "x", [], True])
def test_entry_must_be_a_map(root, entry):
    errs = check_catalog(root, lambda c: c.__setitem__("lead-time", entry))
    assert has(errs, "catalog: lead-time: entry must be a map")


def test_all_errors_are_returned_not_only_the_first(root):
    def bad(c):
        c["lead-time"]["better"] = "down"
        c["lead-time"]["scope"] = "team"
        c["diff-lines"].pop("unit")

    errs = check_catalog(root, bad)
    assert has(errs, "catalog: lead-time.better:") and has(errs, "catalog: lead-time.scope:")
    assert has(errs, "catalog: diff-lines.unit: required")


def test_c4_name_defined_in_two_files(root):
    a = {"lead-time": jload(os.path.join(root, "metrics.json"))["lead-time"]}
    b = {"lead-time": a["lead-time"]}
    errs = vc.validate_catalog([("metrics.json", a), ("metrics.research.json", b)], root)
    assert has(errs, "catalog: lead-time: defined in metrics.json and metrics.research.json")


def test_names_unique_across_files_merge_cleanly(root):
    cat = jload(os.path.join(root, "metrics.json"))
    a = {"lead-time": cat["lead-time"]}
    b = {"diff-lines": cat["diff-lines"]}
    errs = vc.validate_catalog([("a.json", a), ("b.json", b)], root)
    assert errs == []
    merged, merr = vc.merge_catalogs([("a.json", a), ("b.json", b)])
    assert sorted(merged) == ["diff-lines", "lead-time"] and merr == []


def test_merge_catalogs_reports_labels_in_argument_order(root):
    merged, errs = vc.merge_catalogs([("z.json", {"x": {}}), ("a.json", {"x": {}})])
    assert errs == ["catalog: x: defined in z.json and a.json"]
    assert merged == {"x": {}}


@pytest.mark.parametrize("value", [[], "x", 3, None])
def test_file_that_is_not_a_map(root, value):
    errs = vc.validate_catalog([("bad.json", value)], root)
    assert errs == ["catalog bad.json: must be a map of metric names"]
    _, merr = vc.merge_catalogs([("bad.json", value)])
    assert merr == ["catalog bad.json: must be a map of metric names"]


def test_non_string_key_is_reported_and_stops_other_checks(root):
    errs = vc.validate_catalog([("m.json", {True: {"scope": "x"}})], root)
    assert errs, "expected a shape error"
    assert "is not a string" in errs[0] and "quote it" in errs[0]
    assert not has(errs, "catalog: True")


def test_non_json_value_is_reported(root):
    errs = vc.validate_catalog([("m.json", {"a": {"unit": {1, 2}}})], root)
    assert any("value of type set is not JSON" in e for e in errs)


def test_non_finite_number_is_reported(root):
    errs = vc.validate_catalog([("m.json", {"a": {"unit": float("inf")}})], root)
    assert any("non-finite number" in e for e in errs)


def test_nesting_deeper_than_128_levels_is_reported_once_without_recursion(root):
    deep = []
    cur = deep
    for _ in range(300):
        nxt = []
        cur.append(nxt)
        cur = nxt
    errs = vc.validate_catalog([("m.json", {"a": {"unit": deep}})], root)
    assert sum("nested deeper than 128 levels" in e for e in errs) == 1


@pytest.mark.parametrize("entry", [
    {"scope": [], "better": {}, "reads": [[]], "collector": 5, "unit": None, "formula": []},
    {"scope": {"a": 1}, "better": [1], "reads": [{}], "collector": {}, "unit": {}, "formula": {}},
    {"reads": "x" * 10, "collector": "collectors/\x00"},
])
def test_catalog_never_raises_on_odd_values(root, entry):
    assert isinstance(vc.validate_catalog([("m.json", {"a": entry})], root), list)


# ---------------------------------------------------------------- manifest: fixture and top level


def test_fixture_manifest_validates(root):
    assert check_manifest(root) == []


@pytest.mark.parametrize("value", [[], "x", 3, None])
def test_manifest_that_is_not_a_map_stops_at_once(root, value, catalog):
    assert vm.validate_manifest(value, catalog, root) == ["manifest: must be a map"]


@pytest.mark.parametrize("key", ["owner", "namespace", "roles", "workflows", "vetoes"])
def test_missing_required_top_level_key(root, key):
    errs = check_manifest(root, lambda m: m.pop(key))
    assert has(errs, f"manifest: {key}: required")


def test_targets_may_be_absent(root):
    assert check_manifest(root, lambda m: m.pop("targets")) == []


def test_m9_stack_key_is_unknown(root):
    errs = check_manifest(root, lambda m: m.__setitem__("stack", {}))
    assert has(errs, "manifest: unknown key 'stack'")


@pytest.mark.parametrize("value", ["", "   ", None, 3, ["x"]])
def test_owner_must_be_a_non_empty_string(root, value):
    errs = check_manifest(root, lambda m: m.__setitem__("owner", value))
    assert has(errs, "manifest: owner: must be a non-empty string")


@pytest.mark.parametrize("value", ["", "-a", "a-", "a b", "a_b", 3, None, "a" * 64])
def test_namespace_pattern(root, value):
    errs = check_manifest(root, lambda m: m.__setitem__("namespace", value))
    assert has(errs, "manifest: namespace: must match the OWS namespace pattern")


@pytest.mark.parametrize("key", ["roles", "workflows"])
@pytest.mark.parametrize("value", [{}, [], "x", None])
def test_roles_and_workflows_must_be_non_empty_maps(root, key, value):
    errs = check_manifest(root, lambda m: m.__setitem__(key, value))
    assert has(errs, f"manifest: {key}: must be a non-empty map")


# ---------------------------------------------------------------- manifest: vetoes


def test_m4_empty_vetoes(root):
    errs = check_manifest(root, lambda m: m.__setitem__("vetoes", []))
    assert has(errs, "manifest: vetoes: must be a non-empty list of strings")


@pytest.mark.parametrize("value", [[""], ["  "], [1], ["ok", ""], "x", None, {"a": "b"}])
def test_vetoes_must_hold_non_empty_strings(root, value):
    errs = check_manifest(root, lambda m: m.__setitem__("vetoes", value))
    assert has(errs, "manifest: vetoes: must be a non-empty list of strings")


# ---------------------------------------------------------------- manifest: role ladder


def test_m1_escalation_cycle(root):
    errs = check_manifest(root, lambda m: m["roles"]["lead"].__setitem__("escalates-to", "worker"))
    assert has(errs, "manifest: roles.lead: escalation chain never reaches owner")
    assert has(errs, "manifest: roles.worker: escalation chain never reaches owner")


def test_self_escalation_never_reaches_owner(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].__setitem__("escalates-to", "pm"))
    assert has(errs, "manifest: roles.pm: escalation chain never reaches owner")


def test_m2_spawn_upward_is_refused(root):
    errs = check_manifest(root, lambda m: m["roles"]["worker"].__setitem__("may-spawn", ["lead"]))
    assert has(errs, "manifest: roles.worker.may-spawn: 'lead' is not below worker on the ladder")


def test_spawn_of_a_sibling_is_refused(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].__setitem__("may-spawn", ["tester"]))
    assert has(errs, "manifest: roles.pm.may-spawn: 'tester' is not below pm on the ladder")


def test_spawn_of_a_role_that_escalates_through_you_is_allowed(root):
    def grow(m):
        m["roles"]["junior"] = {"escalates-to": "worker"}
        m["roles"]["worker"]["may-spawn"] = ["junior"]
        m["roles"]["lead"]["may-spawn"].append("junior")

    assert check_manifest(root, grow) == []


def test_spawning_yourself_is_allowed(root):
    assert check_manifest(root, lambda m: m["roles"]["worker"].__setitem__("may-spawn", ["worker"])) == []


def test_m5_declaring_owner_is_refused(root):
    errs = check_manifest(root, lambda m: m["roles"].__setitem__("owner", {"escalates-to": "lead"}))
    assert has(errs, "manifest: roles.owner: 'owner' is reserved for the top rung; do not declare it")


def test_m10_owner_cannot_be_spawned(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].__setitem__("may-spawn", ["owner"]))
    assert has(errs, "manifest: roles.pm.may-spawn: 'owner' cannot be spawned")


def test_role_name_must_be_kebab_case(root):
    errs = check_manifest(root, lambda m: m["roles"].__setitem__("Bad_Role", {"escalates-to": "lead"}))
    assert has(errs, "manifest: roles.Bad_Role: name must be kebab-case")


def test_escalates_to_is_required(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].pop("escalates-to"))
    assert has(errs, "manifest: roles.pm.escalates-to: required")


def test_escalates_to_unknown_role(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].__setitem__("escalates-to", "boss"))
    assert has(errs, "manifest: roles.pm.escalates-to: unknown role 'boss'")


def test_may_spawn_must_be_a_list(root):
    errs = check_manifest(root, lambda m: m["roles"]["lead"].__setitem__("may-spawn", "worker"))
    assert has(errs, "manifest: roles.lead.may-spawn: must be a list of roles")


def test_may_spawn_unknown_role(root):
    errs = check_manifest(root, lambda m: m["roles"]["lead"]["may-spawn"].append("ghost"))
    assert has(errs, "manifest: roles.lead.may-spawn: unknown role 'ghost'")


def test_role_entry_unknown_key_and_non_map(root):
    errs = check_manifest(root, lambda m: m["roles"]["pm"].__setitem__("rank", 1))
    assert has(errs, "manifest: roles.pm: unknown key 'rank'")
    errs = check_manifest(root, lambda m: m["roles"].__setitem__("pm", "lead"))
    assert has(errs, "manifest: roles.pm: must be a map")


def test_chain_and_spawn_checks_wait_for_the_shape_checks(root):
    def bad(m):
        m["roles"]["lead"]["escalates-to"] = "worker"  # cycle
        m["roles"]["pm"]["may-spawn"] = ["ghost"]  # shape error

    errs = check_manifest(root, bad)
    assert has(errs, "manifest: roles.pm.may-spawn: unknown role 'ghost'")
    assert not has(errs, "manifest: roles.lead: escalation chain never reaches owner")


def test_spawn_check_waits_for_the_chain_check(root):
    def bad(m):
        m["roles"]["lead"]["escalates-to"] = "worker"
        m["roles"]["worker"]["may-spawn"] = ["lead"]

    errs = check_manifest(root, bad)
    assert has(errs, "manifest: roles.lead: escalation chain never reaches owner")
    assert not any("is not below" in e for e in errs)


def test_a_role_may_spawn_all_its_subordinates_through_two_rungs(root):
    # lead -> pm -> worker2: lead may spawn worker2, two rungs down.
    def grow(m):
        m["roles"]["worker2"] = {"escalates-to": "pm"}
        m["roles"]["lead"]["may-spawn"].append("worker2")

    assert check_manifest(root, grow) == []


@pytest.mark.parametrize("bad", [["x"], {"a": 1}, 3])
def test_unhashable_role_names_do_not_raise(root, bad):
    def go(m):
        m["roles"]["pm"]["escalates-to"] = bad
        m["roles"]["lead"]["may-spawn"] = [bad]

    errs = check_manifest(root, go)
    assert has(errs, "manifest: roles.pm.escalates-to: unknown role")
    assert has(errs, "manifest: roles.lead.may-spawn: unknown role")


# ---------------------------------------------------------------- manifest: targets


def test_m3_target_on_an_unknown_metric(root):
    errs = check_manifest(root, lambda m: m["targets"].__setitem__("speed", {"at-most": 1}))
    assert has(errs, "manifest: targets.speed: unknown metric 'speed'")


def test_target_on_every_appendix_a_metric_is_accepted(root):
    def all_targets(m):
        m["targets"] = {n: {"at-most": 3} for n in APPENDIX_A}

    assert check_manifest(root, all_targets) == []


def test_target_unknown_metric_is_judged_against_the_catalog_given(root):
    errs = check_manifest(root, mutate_catalog=lambda c: c.pop("spec-rework"))
    assert has(errs, "manifest: targets.spec-rework: unknown metric 'spec-rework'")


@pytest.mark.parametrize("catalog_arg", [None, [], "x", 3])
def test_catalog_that_is_not_a_map_reads_as_empty(root, manifest, catalog_arg):
    errs = vm.validate_manifest(manifest, catalog_arg, root)
    assert has(errs, "manifest: targets.spec-rework: unknown metric 'spec-rework'")


def test_m6_both_bounds(root):
    errs = check_manifest(root, lambda m: m["targets"]["spec-rework"].__setitem__("at-least", 0))
    assert has(errs, "manifest: targets.spec-rework: exactly one of at-least, at-most")


def test_target_with_no_bound(root):
    errs = check_manifest(root, lambda m: m["targets"].__setitem__("spec-rework", {"per": "item"}))
    assert has(errs, "manifest: targets.spec-rework: exactly one of at-least, at-most")


@pytest.mark.parametrize("value", ["1", True, False, None, [1]])
def test_target_bound_must_be_a_finite_number(root, value):
    errs = check_manifest(root, lambda m: m["targets"].__setitem__("spec-rework", {"at-most": value}))
    assert has(errs, "manifest: targets.spec-rework.at-most: must be a finite number")


@pytest.mark.parametrize("value", [float("inf"), float("nan"), float("-inf")])
def test_non_finite_target_bound_is_a_shape_error(root, value):
    errs = check_manifest(root, lambda m: m["targets"].__setitem__("spec-rework", {"at-most": value}))
    assert has(errs, "manifest: targets.spec-rework.at-most: non-finite number")


@pytest.mark.parametrize("value", [0, 1, 1.5, -2, 0.0])
def test_target_bound_accepts_numbers(root, value):
    assert check_manifest(root, lambda m: m["targets"].__setitem__("spec-rework", {"at-least": value})) == []


@pytest.mark.parametrize("value", ["day", "", None, 1, ["item"]])
def test_target_per_outside_the_closed_set(root, value):
    errs = check_manifest(root, lambda m: m["targets"]["spec-rework"].__setitem__("per", value))
    assert has(errs, f"manifest: targets.spec-rework.per: {value!r} is not one of item, run, unit")


@pytest.mark.parametrize("per", ["item", "run", "unit"])
def test_target_per_accepts_the_closed_set(root, per):
    assert check_manifest(root, lambda m: m["targets"]["spec-rework"].__setitem__("per", per)) == []


def test_target_unknown_key_and_non_map(root):
    errs = check_manifest(root, lambda m: m["targets"]["spec-rework"].__setitem__("by", 1))
    assert has(errs, "manifest: targets.spec-rework: unknown key 'by'")
    errs = check_manifest(root, lambda m: m["targets"].__setitem__("spec-rework", 1))
    assert has(errs, "manifest: targets.spec-rework: must be a map")


@pytest.mark.parametrize("value", [[], "x", 1, None])
def test_targets_must_be_a_map(root, value):
    errs = check_manifest(root, lambda m: m.__setitem__("targets", value))
    assert has(errs, "manifest: targets: must be a map")


# ---------------------------------------------------------------- manifest: workflow entries


def test_m7_workflow_file_missing(root):
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("path", "workflows/gone.yaml"))
    assert has(errs, "manifest: workflows.improve.path: file not found under root: workflows/gone.yaml")


def test_missing_file_adds_no_load_or_cycle_noise(root):
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("path", "workflows/gone.json"))
    assert [e for e in errs if "improve" in e] == [
        "manifest: workflows.improve.path: file not found under root: workflows/gone.json"
    ]


def test_m8_floors_required_even_when_empty(root):
    errs = check_manifest(root, lambda m: m["workflows"]["tdd-unit"].pop("floors"))
    assert has(errs, "manifest: workflows.tdd-unit.floors: required")


def test_path_required(root):
    errs = check_manifest(root, lambda m: m["workflows"]["tdd-unit"].pop("path"))
    assert has(errs, "manifest: workflows.tdd-unit.path: required")


@pytest.mark.parametrize("path", [
    "/abs/x.yaml", "workflows/../x.yaml", "other/x.yaml", "workflows/x.txt", "workflows/.yaml", "workflows\\x.yaml",
    "workflows/x\x00.yaml", 5, None,
])
def test_path_form(root, path):
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("path", path))
    assert has(errs, "manifest: workflows.improve.path: must be a relative path under workflows/ ending .yaml, .yml or .json")


@pytest.mark.parametrize("value", ["x", [1], [""], ["Bad_Name"], None, {"a": 1}])
def test_floors_must_be_a_list_of_task_names(root, value):
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("floors", value))
    assert has(errs, "manifest: workflows.improve.floors: must be a list of task names")


def test_floors_duplicate(root):
    errs = check_manifest(root, lambda m: m["workflows"]["sw-development"].__setitem__("floors", ["a", "a"]))
    assert has(errs, "manifest: workflows.sw-development.floors: duplicate task name")


def test_m16_workflow_name_must_be_kebab_case(root):
    def add(m):
        m["workflows"]["Improve_X"] = {"path": "workflows/improve.json", "floors": []}

    errs = check_manifest(root, add)
    assert has(errs, "manifest: workflows.Improve_X: name must be kebab-case")


def test_workflow_entry_unknown_key_and_non_map(root):
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("stack", {}))
    assert has(errs, "manifest: workflows.improve: unknown key 'stack'")
    errs = check_manifest(root, lambda m: m["workflows"].__setitem__("improve", "x"))
    assert has(errs, "manifest: workflows.improve: must be a map")


def test_workflow_path_may_point_inside_a_subdirectory(root):
    os.makedirs(os.path.join(root, "workflows", "sub"))
    shutil.copy(os.path.join(root, "workflows", "improve.json"), os.path.join(root, "workflows", "sub", "improve.json"))
    assert check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("path", "workflows/sub/improve.json")) == []


def test_workflow_symlink_leaving_the_root_is_refused(root, tmp_path):
    outside = tmp_path / "outside.json"
    shutil.copy(os.path.join(root, "workflows", "improve.json"), outside)
    os.symlink(outside, os.path.join(root, "workflows", "link.json"))
    errs = check_manifest(root, lambda m: m["workflows"]["improve"].__setitem__("path", "workflows/link.json"))
    assert has(errs, "manifest: workflows.improve.path: file not found under root: workflows/link.json")


# ---------------------------------------------------------------- manifest: loaded workflows


def test_m11_document_name_must_equal_the_key(root):
    errs = check_manifest(
        root, lambda m: m["workflows"]["tdd-unit"].__setitem__("path", "workflows/sw-development.json"))
    assert has(errs, "manifest: workflows.tdd-unit.path: document.name is 'sw-development', expected 'tdd-unit'")


@pytest.mark.parametrize("doc", [{"do": []}, {"document": [], "do": []}, {"document": {"name": None}, "do": []}])
def test_document_name_missing_prints_none(root, doc):
    jdump(os.path.join(root, "workflows", "improve.json"), doc)
    errs = check_manifest(root)
    assert has(errs, "manifest: workflows.improve.path: document.name is None, expected 'improve'")


def test_m15_duplicate_key_in_a_workflow_is_a_located_load_error(root):
    set_improve(root, None, raw='{"document": {"name": "improve"}, "do": [], "a": 1, "a": 2}')
    errs = check_manifest(root)
    assert has(errs, "manifest: workflows.improve.path: duplicate key 'a'")
    assert not any(root in e for e in errs), "the file label must be stripped"


def test_workflow_parse_error(root):
    set_improve(root, None, raw="{not json")
    errs = check_manifest(root)
    assert has(errs, "manifest: workflows.improve.path: parse error: ")


def test_workflow_non_finite_number(root):
    set_improve(root, None, raw='{"document": {"name": "improve"}, "do": [], "x": NaN}')
    assert has(check_manifest(root), "manifest: workflows.improve.path: non-finite number NaN")


@pytest.mark.parametrize("raw", ["[]", '"x"', "3", "null"])
def test_workflow_that_is_not_a_map(root, raw):
    set_improve(root, None, raw=raw)
    assert has(check_manifest(root), "manifest: workflows.improve.path: workflow must be a map")


def test_m17_task_item_must_be_a_map_with_one_name(root):
    set_improve(root, ["x", {"ok": {"set": {"a": 1}}}])
    assert has(check_manifest(root), "manifest: workflows.improve.path: [0]: task item must be a map with one name")


def test_task_item_with_two_names(root):
    set_improve(root, [{"a": {"set": {}}, "b": {"set": {}}}])
    assert has(check_manifest(root), "manifest: workflows.improve.path: [0]: task item must be a map with one name")


def test_nested_task_item_error_names_the_parent_path(root):
    set_improve(root, [{"outer": {"do": [1]}}])
    assert has(check_manifest(root), "manifest: workflows.improve.path: outer/[0]: task item must be a map with one name")


def test_task_that_is_not_a_map(root):
    set_improve(root, [{"x": 5}])
    assert has(check_manifest(root), "manifest: workflows.improve.path: x: task must be a map")


@pytest.mark.parametrize("task", [
    {"do": "x"}, {"do": {"a": 1}}, {"fork": {"branches": "x"}}, {"try": "x"}, {"try": [], "catch": {"do": "x"}},
])
def test_task_list_that_is_not_a_list(root, task):
    set_improve(root, [{"x": task}])
    assert has(check_manifest(root), "manifest: workflows.improve.path: x: task list must be a list"), task


def test_top_level_do_that_is_not_a_list(root):
    jdump(os.path.join(root, "workflows", "improve.json"),
          {"document": {"name": "improve"}, "do": {"a": 1}})
    assert has(check_manifest(root), "manifest: workflows.improve.path: do: task list must be a list")


def test_walk_goes_on_after_a_bad_item(root):
    set_improve(root, ["x", {"b": {"run": {"workflow": {"namespace": "org", "name": "sw-development"}}}}])
    errs = check_manifest(root)
    assert has(errs, "manifest: workflows.improve.path: [0]")
    assert has(errs, "manifest: workflows: start cycle 'improve' -> 'sw-development' -> 'improve'")


def _nest(depth, leaf):
    task = leaf
    for i in range(depth, 0, -1):
        task = {"do": [{f"n{i}": task}]}
    return task


def test_list_16_is_valid_and_list_17_is_refused(root):
    # The top-level do is list 1. Each _nest level adds one list, so the leaf of _nest(15) is in list 16.
    ok = [{"n1": _nest(15, {"set": {"a": 1}})}]
    set_improve(root, ok)
    assert not any("nesting" in e for e in check_manifest(root))
    too_deep = [{"n1": _nest(16, {"set": {"a": 1}})}]
    set_improve(root, too_deep)
    assert any("nesting deeper than 16 task lists" in e for e in check_manifest(root))


def test_walk_reads_catch_do_try_and_fork_branches(root):
    call = {"run": {"workflow": {"namespace": "org", "name": "sw-development"}}}
    for task in (
        {"try": [{"c": call}]},
        {"try": [], "catch": {"do": [{"c": call}]}},
        {"fork": {"branches": [{"c": call}]}},
        {"for": {"each": "i", "in": [1]}, "do": [{"c": call}]},
    ):
        set_improve(root, [{"outer": task}])
        assert has(check_manifest(root), "manifest: workflows: start cycle 'improve' -> 'sw-development' -> 'improve'"), task


# ---------------------------------------------------------------- manifest: start cycles


CALL_SW = {"run": {"workflow": {"namespace": "org", "name": "sw-development", "version": "latest"}}}


def test_m12_call_cycle(root):
    set_improve(root, [{"back": CALL_SW}])
    errs = check_manifest(root)
    assert "manifest: workflows: start cycle 'improve' -> 'sw-development' -> 'improve'" in errs


def test_m13_emit_that_starts_another_workflow_closes_a_cycle(root):
    set_improve(root, [{"again": {"emit": {"event": {"with": {"type": "org.work-item-ready"}}}}}])
    errs = check_manifest(root)
    assert "manifest: workflows: start cycle 'improve' -> 'sw-development' -> 'improve'" in errs


def test_m14_emit_of_a_type_a_decision_gate_listens_on(root):
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.owner-decided"}}}}}])
    errs = check_manifest(root)
    assert "manifest: workflows.improve: emit 'e' type 'org.owner-decided' is listened on by gate 'sw-development:merge-gate'" in errs


def test_m18_self_call(root):
    set_improve(root, [{"again": {"run": {"workflow": {"namespace": "org", "name": "improve"}}}}])
    errs = check_manifest(root)
    assert "manifest: workflows: start cycle 'improve' -> 'improve'" in errs


def test_acyclic_calls_and_emits_are_valid(root):
    # sw-development already calls improve and tdd-unit; add a non-cyclic emit of an unrelated type.
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.something-else"}}}}}])
    assert check_manifest(root) == []


def test_non_literal_emit_type_adds_no_edge_and_no_entry(root):
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "${ .t }"}}}}}])
    assert check_manifest(root) == []


def test_non_literal_gate_type_is_not_indexed(root):
    sw = jload(os.path.join(root, "workflows", "sw-development.json"))
    gate = next(t["merge-gate"] for t in sw["do"] if "merge-gate" in t)
    gate["listen"]["to"]["one"]["with"]["type"] = "${ .t }"
    jdump(os.path.join(root, "workflows", "sw-development.json"), sw)
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.owner-decided"}}}}}])
    assert check_manifest(root) == []


def test_plain_gate_may_listen_on_an_emitted_type(root):
    sw = jload(os.path.join(root, "workflows", "sw-development.json"))
    gate = next(t["merge-gate"] for t in sw["do"] if "merge-gate" in t)
    gate["metadata"]["org"]["role"] = "lead"  # no longer a decision gate: no human item, role not owner
    jdump(os.path.join(root, "workflows", "sw-development.json"), sw)
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.owner-decided"}}}}}])
    assert not any("is listened on by gate" in e for e in check_manifest(root))


def test_decision_gate_by_human_acceptance_item(root):
    sw = jload(os.path.join(root, "workflows", "sw-development.json"))
    gate = next(t["merge-gate"] for t in sw["do"] if "merge-gate" in t)
    gate["metadata"]["org"] = {"role": "lead", "acceptance": [{"human": "owner decides"}]}
    jdump(os.path.join(root, "workflows", "sw-development.json"), sw)
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.owner-decided"}}}}}])
    assert any("is listened on by gate 'sw-development:merge-gate'" in e for e in check_manifest(root))


def test_decision_gate_listening_through_to_any(root):
    sw = jload(os.path.join(root, "workflows", "sw-development.json"))
    gate = next(t["merge-gate"] for t in sw["do"] if "merge-gate" in t)
    gate["listen"]["to"] = {"any": [{"with": {"type": "org.a"}}, {"with": {"type": "org.b"}}]}
    jdump(os.path.join(root, "workflows", "sw-development.json"), sw)
    set_improve(root, [{"e": {"emit": {"event": {"with": {"type": "org.b"}}}}}])
    assert any("emit 'e' type 'org.b' is listened on by gate" in e for e in check_manifest(root))


def test_emit_in_the_gates_own_workflow_is_left_to_validate_org(root):
    sw = jload(os.path.join(root, "workflows", "sw-development.json"))
    sw["do"].append({"forge": {"emit": {"event": {"with": {"type": "org.owner-decided"}}}}})
    jdump(os.path.join(root, "workflows", "sw-development.json"), sw)
    assert not any("is listened on by gate" in e for e in check_manifest(root))


def _three_workflow_root(root, edges):
    """Rewrite the workflows as the names in `edges`, with `edges` = {name: [called names]}."""
    for f in os.listdir(os.path.join(root, "workflows")):
        os.remove(os.path.join(root, "workflows", f))
    man = jload(os.path.join(root, "manifest.json"))
    man["workflows"] = {}
    for name, calls in edges.items():
        tasks = [{f"c{i}": {"run": {"workflow": {"namespace": "org", "name": t}}}} for i, t in enumerate(calls)]
        jdump(os.path.join(root, "workflows", f"{name}.json"),
              {"document": {"dsl": "1.1.0", "namespace": "org", "name": name, "version": "0.1.0"}, "do": tasks})
        man["workflows"][name] = {"path": f"workflows/{name}.json", "floors": []}
    cat = jload(os.path.join(root, "metrics.json"))
    return vm.validate_manifest(man, cat, root)


def test_cycle_error_names_the_shortest_path_from_the_back_edge_target(root):
    # DFS from a goes a -> b -> c, and c -> a is the first back edge. The shortest path from a to c is a -> c.
    errs = _three_workflow_root(root, {"a": ["b", "c"], "b": ["c"], "c": ["a"]})
    assert [e for e in errs if "start cycle" in e] == ["manifest: workflows: start cycle 'a' -> 'c' -> 'a'"]


def test_only_one_cycle_error_is_reported(root):
    errs = _three_workflow_root(root, {"a": ["b"], "b": ["a"], "c": ["c"]})
    assert len([e for e in errs if "start cycle" in e]) == 1
    assert "manifest: workflows: start cycle 'a' -> 'b' -> 'a'" in errs


def test_a_dag_has_no_cycle(root):
    errs = _three_workflow_root(root, {"a": ["b", "c"], "b": ["c"], "c": []})
    assert not any("start cycle" in e for e in errs)


def test_call_to_an_unlisted_workflow_adds_no_edge_and_no_error_here(root):
    errs = _three_workflow_root(root, {"a": ["ghost"]})
    assert errs == []


def test_unhashable_call_name_does_not_raise(root):
    set_improve(root, [{"c": {"run": {"workflow": {"namespace": "org", "name": ["x"]}}}}])
    assert isinstance(check_manifest(root), list)


# ---------------------------------------------------------------- loader


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def load_msg(path):
    with pytest.raises(vc.LoadError) as ei:
        vc.load_document(path)
    return str(ei.value)


def test_l1_json_duplicate_key(tmp_path):
    p = write(tmp_path, "a.json", '{"a": 1, "a": 2}')
    assert load_msg(p) == f"{p}: duplicate key 'a'"


def test_l1_nested_json_duplicate_key(tmp_path):
    p = write(tmp_path, "a.json", '{"x": [{"b": 1, "b": 2}]}')
    assert load_msg(p).endswith("duplicate key 'b'")


def test_l3_json_nan(tmp_path):
    p = write(tmp_path, "a.json", '{"a": NaN}')
    assert load_msg(p) == f"{p}: non-finite number NaN"


@pytest.mark.parametrize("text,word", [("Infinity", "Infinity"), ("-Infinity", "-Infinity")])
def test_json_infinity_constants(tmp_path, text, word):
    p = write(tmp_path, "a.json", '{"a": %s}' % text)
    assert load_msg(p) == f"{p}: non-finite number {word}"


def test_l6_json_overflowing_float(tmp_path):
    p = write(tmp_path, "a.json", '{"a": 1e999}')
    assert load_msg(p) == f"{p}: non-finite number 1e999"


def test_l7_json_nesting_too_deep(tmp_path):
    p = write(tmp_path, "a.json", "[" * 100000)
    assert load_msg(p) == f"{p}: nesting too deep to load"


def test_l9_json_integer_longer_than_4300_digits(tmp_path):
    p = write(tmp_path, "a.json", '{"a": %s}' % ("9" * 5000))
    assert load_msg(p) == f"{p}: integer longer than 4300 digits"


def test_json_parse_error_names_the_first_line_only(tmp_path):
    p = write(tmp_path, "a.json", "{not json\n")
    msg = load_msg(p)
    assert msg.startswith(f"{p}: parse error: ") and "\n" not in msg


def test_unreadable_file_is_a_load_error(tmp_path):
    p = str(tmp_path / "missing.json")
    assert load_msg(p).startswith(f"{p}: ")


def test_valid_json_loads(tmp_path):
    p = write(tmp_path, "a.json", '{"a": [1, 2.5, "x", null, true]}')
    assert vc.load_document(p) == {"a": [1, 2.5, "x", None, True]}


def test_unknown_extension_is_a_usage_error(tmp_path):
    p = write(tmp_path, "a.toml", "a = 1")
    with pytest.raises(vc.UsageError):
        vc.load_document(p)


def _need_yaml():
    return pytest.importorskip("yaml", reason="PyYAML is needed to test the YAML loader")


def test_l2_yaml_duplicate_key(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: 1\na: 2\n")
    assert load_msg(p) == f"{p}: duplicate key 'a'"


def test_l5_yaml_alias(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: &x [1]\nb: *x\n")
    assert load_msg(p) == f"{p}: alias '*x' is not accepted; write the value out"


def test_yaml_anchor_without_alias_loads(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: &x [1]\nb: [2]\n")
    assert vc.load_document(p) == {"a": [1], "b": [2]}


def test_l8_yaml_merge_key(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: &x {a: 1}\nb:\n  <<: {a: 1}\n  c: 2\n")
    assert load_msg(p) == f"{p}: merge key '<<' is not accepted; write the keys out"


def test_l10_yaml_integer_longer_than_4300_digits(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: %s\n" % ("9" * 5000))
    assert load_msg(p) == f"{p}: integer longer than 4300 digits"


def test_l11_yaml_unclosed_flow(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: [\n")
    msg = load_msg(p)
    assert msg.startswith(f"{p}: parse error: ") and "\n" not in msg


def test_yaml_nesting_too_deep(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: " + "[" * 20000 + "]" * 20000 + "\n")
    assert "nesting too deep to load" in load_msg(p) or "parse error" in load_msg(p)


def test_yaml_positive_control_keeps_strings(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a: 2026-11-19\nb: on\nc: yes\nd: true\ne: False\nf: no\n")
    assert vc.load_document(p) == {"a": "2026-11-19", "b": "on", "c": "yes", "d": True, "e": False, "f": "no"}


def test_yaml_loader_does_not_change_plain_safe_load(tmp_path):
    yaml_mod = _need_yaml()
    p = write(tmp_path, "a.yaml", "b: on\n")
    vc.load_document(p)
    assert yaml_mod.safe_load("b: on\n") == {"b": True}


def test_yaml_nested_sequences_inside_maps_build_fully(tmp_path):
    _need_yaml()
    p = write(tmp_path, "a.yaml", "a:\n  - b: [1, 2]\n    c: {d: [3]}\n")
    assert vc.load_document(p) == {"a": [{"b": [1, 2], "c": {"d": [3]}}]}


def test_yaml_manifest_example_validates(root, tmp_path):
    yaml_mod = _need_yaml()
    man = jload(os.path.join(root, "manifest.json"))
    for w in man["workflows"].values():
        w["path"] = w["path"].replace(".json", ".yaml")
    for name in ("sw-development", "tdd-unit", "improve"):
        doc = jload(os.path.join(root, "workflows", f"{name}.json"))
        (Path(root) / "workflows" / f"{name}.yaml").write_text(yaml_mod.safe_dump(doc), encoding="utf-8")
    p = Path(root) / "manifest.yaml"
    p.write_text(yaml_mod.safe_dump(man), encoding="utf-8")
    cat = jload(os.path.join(root, "metrics.json"))
    assert vm.validate_manifest(vc.load_document(str(p)), cat, root) == []


# ---------------------------------------------------------------- command lines


def run_cli(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)


def test_catalog_cli_valid_prints_nothing_and_exits_0(root):
    r = run_cli("validate_catalog.py", "--root", root, os.path.join(root, "metrics.json"))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_catalog_cli_invalid_prints_error_lines_and_exits_1(root):
    cat = jload(os.path.join(root, "metrics.json"))
    cat["lead-time"]["better"] = "down"
    bad = os.path.join(root, "bad.json")
    jdump(bad, cat)
    r = run_cli("validate_catalog.py", "--root", root, bad)
    assert r.returncode == 1
    assert "ERROR: catalog: lead-time.better: 'down' is not one of context, higher, lower" in r.stderr.splitlines()


def test_catalog_cli_merges_several_files(root):
    cat = jload(os.path.join(root, "metrics.json"))
    a, b = os.path.join(root, "a.json"), os.path.join(root, "b.json")
    jdump(a, {"lead-time": cat["lead-time"]})
    jdump(b, {"lead-time": cat["lead-time"]})
    r = run_cli("validate_catalog.py", "--root", root, a, b)
    assert r.returncode == 1
    assert f"ERROR: catalog: lead-time: defined in {a} and {b}" in r.stderr


def test_catalog_cli_load_error_exits_1_with_file_label(root):
    bad = os.path.join(root, "bad.json")
    Path(bad).write_text('{"a": 1, "a": 2}')
    r = run_cli("validate_catalog.py", "--root", root, bad)
    assert r.returncode == 1 and f"ERROR: {bad}: duplicate key 'a'" in r.stderr


def test_catalog_cli_unknown_extension_exits_2(root):
    bad = os.path.join(root, "m.toml")
    Path(bad).write_text("a = 1")
    r = run_cli("validate_catalog.py", "--root", root, bad)
    assert r.returncode == 2


def test_catalog_cli_without_files_is_a_usage_error(root):
    assert run_cli("validate_catalog.py", "--root", root).returncode == 2


def test_catalog_cli_missing_root_flag_is_a_usage_error(root):
    assert run_cli("validate_catalog.py", os.path.join(root, "metrics.json")).returncode == 2


def test_manifest_cli_valid(root):
    r = run_cli("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"),
                os.path.join(root, "manifest.json"))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_manifest_cli_invalid(root):
    man = jload(os.path.join(root, "manifest.json"))
    man["targets"]["speed"] = {"at-most": 1}
    p = os.path.join(root, "bad-manifest.json")
    jdump(p, man)
    r = run_cli("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"), p)
    assert r.returncode == 1
    assert "ERROR: manifest: targets.speed: unknown metric 'speed'" in r.stderr.splitlines()


def test_manifest_cli_catalog_merge_error_is_printed_without_a_file_prefix(root):
    cat = jload(os.path.join(root, "metrics.json"))
    a, b = os.path.join(root, "a.json"), os.path.join(root, "b.json")
    jdump(a, cat)
    jdump(b, {"lead-time": cat["lead-time"]})
    r = run_cli("validate_manifest.py", "--root", root, "--catalog", a, "--catalog", b,
                os.path.join(root, "manifest.json"))
    assert r.returncode == 1
    assert f"ERROR: catalog: lead-time: defined in {a} and {b}" in r.stderr.splitlines()


def test_manifest_cli_manifest_load_error(root):
    p = os.path.join(root, "bad-manifest.json")
    Path(p).write_text('{"owner": 1, "owner": 2}')
    r = run_cli("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"), p)
    assert r.returncode == 1 and f"ERROR: {p}: duplicate key 'owner'" in r.stderr


def test_manifest_cli_requires_a_catalog(root):
    r = run_cli("validate_manifest.py", "--root", root, os.path.join(root, "manifest.json"))
    assert r.returncode == 2


def test_manifest_cli_manifest_that_is_not_a_map(root):
    p = os.path.join(root, "list.json")
    Path(p).write_text("[]")
    r = run_cli("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"), p)
    assert r.returncode == 1 and "ERROR: manifest: must be a map" in r.stderr


NO_YAML = (
    "import sys, runpy\n"
    "sys.modules['yaml'] = None\n"  # makes `import yaml` raise ImportError
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


def run_without_yaml(script, *args):
    return subprocess.run([sys.executable, "-c", NO_YAML, str(SCRIPTS / script), *args], capture_output=True, text=True)


def test_l4_yaml_without_pyyaml_exits_2_with_the_install_hint(root):
    m = os.path.join(root, "m.yaml")
    Path(m).write_text("a: {}\n")
    r = run_without_yaml("validate_catalog.py", "--root", root, m)
    assert r.returncode == 2
    assert f"ERROR: {m}: reading YAML needs PyYAML; run with uv run --with pyyaml, or convert the file to JSON" in r.stderr


def test_yaml_manifest_without_pyyaml_exits_2(root):
    m = os.path.join(root, "manifest.yaml")
    Path(m).write_text("a: {}\n")
    r = run_without_yaml("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"), m)
    assert r.returncode == 2 and "reading YAML needs PyYAML" in r.stderr


def test_yaml_workflow_without_pyyaml_exits_2(root):
    man = jload(os.path.join(root, "manifest.json"))
    man["workflows"]["improve"]["path"] = "workflows/improve.yaml"
    Path(os.path.join(root, "workflows", "improve.yaml")).write_text("do: []\n")
    p = os.path.join(root, "m2.json")
    jdump(p, man)
    r = run_without_yaml("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"), p)
    assert r.returncode == 2 and "reading YAML needs PyYAML" in r.stderr


def test_json_only_runs_do_not_need_pyyaml(root):
    r = run_without_yaml("validate_manifest.py", "--root", root, "--catalog", os.path.join(root, "metrics.json"),
                         os.path.join(root, "manifest.json"))
    assert (r.returncode, r.stderr) == (0, "")


# ---------------------------------------------------------------- the two modules stay stdlib-only


def test_modules_import_only_the_standard_library_at_module_level():
    import ast

    stdlib = set(sys.stdlib_module_names)
    for name in ("validate_catalog.py", "validate_manifest.py"):
        tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
        for node in tree.body:
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [node.module.split(".")[0]]
            for m in mods:
                assert m in stdlib or m == "validate_catalog", f"{name} imports {m} at module level"
