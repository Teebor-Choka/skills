import copy

import pytest
from procedure_testkit import has, validate_text
from validate_procedure import apply_delta, bindings_for, check_bindings, override_violations, parse_procedure
from metrics_fixtures import MET

KEYS = "policy:\n  work.tracker: where issues and work items live\n  vcs.remote: where to push\n  comms.channel: how nodes talk\n"


def proc(top="", stage_extra=""):
    return f"---\nname: t\n{top}stages:\n  a:\n    produces: [x]\n{stage_extra}---\n"


def errs(top="", stage_extra=""):
    return validate_text(proc(top, stage_extra))


# ---- the declaration


def test_a_stage_may_use_a_declared_policy_key():
    assert errs(KEYS, "    uses: [work.tracker, vcs.remote]\n") == []


def test_declared_keys_that_no_stage_uses_are_allowed():
    assert errs(KEYS) == []


def test_a_procedure_without_a_policy_map_is_valid_as_before():
    assert errs() == []


@pytest.mark.parametrize("top", ["policy: text\n", "policy: [a, b]\n", "policy:\n  work.tracker:\n", "policy:\n  work.tracker: [a]\n"])
def test_policy_must_map_each_key_to_a_non_empty_purpose(top):
    assert has(errs(top), "policy")


@pytest.mark.parametrize("key", ["Work Tracker", "work..tracker", ".work", "work.", "-work", "work.Tracker", "1work"])
def test_a_policy_key_must_be_dotted_lowercase_names(key):
    assert has(errs(f"policy:\n  {key}: purpose\n"), "policy")


def test_a_single_name_is_a_valid_key():
    assert errs("policy:\n  vcs: where code lives\n", "    uses: [vcs]\n") == []


# ---- the reference


def test_a_stage_may_not_use_a_key_the_procedure_does_not_declare():
    assert has(errs(KEYS, "    uses: [work.tracker, ghost.key]\n"), "ghost.key")


def test_a_stage_may_not_use_any_key_when_none_are_declared():
    assert has(errs("", "    uses: [work.tracker]\n"), "work.tracker")


@pytest.mark.parametrize("extra", ["    uses: work.tracker\n", "    uses: [true]\n"])
def test_uses_must_be_a_list_of_key_names(extra):
    assert has(errs(KEYS, extra), "uses")


# ---- overlay


BASE, _ = parse_procedure(MET.replace("kpis:", KEYS + "kpis:", 1), "<b>")


def delta(body, window="2 stages"):
    return f"---\nchange:\n  reason: x\n  metrics: [rework]\n  direction: down\n  window: {window}\n{body}---\n"


def test_a_delta_may_add_a_policy_key_and_a_stage_that_uses_it():
    body = "policy:\n  report.sink: where reports go\nstages:\n  lint:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [lint-report]\n    metrics: [rework]\n    uses: [report.sink]\n"
    merged, errors, protected = apply_delta(BASE, delta(body))
    assert errors == [] and "report.sink" in merged["policy"] and "work.tracker" in merged["policy"]


def test_a_delta_may_reword_a_purpose_but_a_stage_cannot_use_what_is_not_there():
    merged, errors, _ = apply_delta(BASE, delta("stages:\n  build:\n    uses: [nowhere.key]\n"))
    assert merged is None and has(errors, "nowhere.key")


def test_where_a_floor_stage_reports_or_pushes_is_locked():
    floor = MET.replace("kpis:", KEYS + "kpis:", 1).replace("  spec:\n    floor: true\n", "  spec:\n    floor: true\n    uses: [work.tracker]\n", 1)
    base, _ = parse_procedure(floor, "<b>")
    merged, errors, protected = apply_delta(base, delta("stages:\n  spec:\n    uses: [vcs.remote]\n"))
    assert protected is True and merged is None


# ---- the policy actually sets each key


POLICY = {"work": {"tracker": "github"}, "vcs": {"remote": "origin"}, "comms": {"channel": "slack"}}


def test_a_policy_that_sets_every_key_passes():
    assert check_bindings(BASE, POLICY) == []


def test_each_missing_key_is_named_with_the_procedure_that_needs_it():
    errors = check_bindings(BASE, {"work": {"tracker": "github"}}, name="sw-development")
    assert has(errors, "vcs.remote") and has(errors, "comms.channel") and has(errors, "sw-development")
    assert not has(errors, "work.tracker")


@pytest.mark.parametrize("value", [None, "", "   ", {}, []])
def test_an_empty_value_counts_as_not_set(value):
    assert has(check_bindings(BASE, {**POLICY, "vcs": {"remote": value}}), "vcs.remote")


@pytest.mark.parametrize("value", [False, "origin", ["a", "b"], {"url": "x"}])
def test_a_real_value_counts_as_set(value):
    assert check_bindings(BASE, {**POLICY, "vcs": {"remote": value}}) == []


def test_a_flat_dotted_policy_key_does_not_count_so_the_hint_says_to_nest_it():
    errors = check_bindings(BASE, {"work.tracker": "github", "vcs": {"remote": "o"}, "comms": {"channel": "c"}})
    assert has(errors, "work.tracker") and has(errors, "nest")


def test_a_procedure_with_no_declared_keys_needs_nothing():
    plain, _ = parse_procedure(MET, "<b>")
    assert check_bindings(plain, {}) == []


# ---- a whole procedure that replaces another must not weaken it


USER = MET


def test_a_replacement_that_keeps_the_protected_set_is_fine():
    user, _ = parse_procedure(USER, "<u>")
    assert override_violations(user, copy.deepcopy(user)) == []


def test_a_replacement_that_drops_a_floor_stage_is_a_violation():
    user, _ = parse_procedure(USER, "<u>")
    mine = copy.deepcopy(user)
    del mine["stages"]["spec"]
    assert has(override_violations(user, mine), "spec")


def test_a_replacement_that_rewires_a_floor_stage_is_a_violation():
    user, _ = parse_procedure(USER, "<u>")
    mine = copy.deepcopy(user)
    mine["stages"]["spec"]["needs"] = []
    assert has(override_violations(user, mine), "spec")


def test_a_replacement_that_unflags_a_floor_stage_is_a_violation():
    user, _ = parse_procedure(USER, "<u>")
    mine = copy.deepcopy(user)
    mine["stages"]["spec"]["floor"] = False
    assert has(override_violations(user, mine), "spec")


@pytest.mark.parametrize("edit, word", [
    (lambda p: p["entities"]["pm"].__setitem__("escalates-to", "worker"), "pm"),
    (lambda p: p["entities"].pop("lead"), "lead"),
    (lambda p: p["loops"]["fix"].__setitem__("on-exhausted", "worker"), "fix"),
    (lambda p: p["loops"].pop("fix"), "fix"),
    (lambda p: p["kpis"]["flow"].__setitem__("owner", "worker"), "flow"),
    (lambda p: p["kpis"].pop("flow"), "flow"),
])
def test_a_replacement_that_moves_the_ladder_loops_or_kpis_is_a_violation(edit, word):
    user, _ = parse_procedure(USER, "<u>")
    mine = copy.deepcopy(user)
    edit(mine)
    assert has(override_violations(user, mine), word)


def test_a_replacement_may_add_stages_entities_and_loops():
    user, _ = parse_procedure(USER, "<u>")
    mine = copy.deepcopy(user)
    mine["stages"]["extra"] = {"entity": "worker", "needs": ["build"], "produces": ["x"], "metrics": ["rework"]}
    mine["entities"]["helper"] = {"escalates-to": "worker"}
    assert override_violations(user, mine) == []


def test_a_replacement_may_lower_but_not_raise_a_loop_bound():
    user, _ = parse_procedure(USER, "<u>")
    lower, higher = copy.deepcopy(user), copy.deepcopy(user)
    lower["loops"]["fix"]["bound"] = "2"
    higher["loops"]["fix"]["bound"] = "9"
    assert override_violations(user, lower) == [] and has(override_violations(user, higher), "bound")


def test_bindings_for_returns_only_the_declared_keys_the_policy_sets():
    got = bindings_for(BASE, {**POLICY, "vcs": {"remote": ""}, "unrelated": "x"})
    assert got == {"comms.channel": "slack", "work.tracker": "github"}


def test_bindings_for_keeps_false_and_structured_values():
    got = bindings_for(BASE, {"work": {"tracker": False}, "vcs": {"remote": ["a"]}, "comms": {"channel": {"url": "x"}}})
    assert got == {"comms.channel": {"url": "x"}, "vcs.remote": ["a"], "work.tracker": False}
