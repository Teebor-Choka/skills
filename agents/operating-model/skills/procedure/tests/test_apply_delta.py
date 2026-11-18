import copy

from procedure_testkit import has
from validate_procedure import apply_delta, parse_procedure
from metrics_fixtures import LINT, MET, change, delta

BASE, _ = parse_procedure(MET, "<base>")


def test_a_valid_delta_returns_the_merged_procedure():
    merged, errs, protected = apply_delta(BASE, delta())
    assert errs == [] and protected is False
    assert "lint" in merged["stages"] and "lint" not in BASE["stages"]


def test_the_base_is_never_changed():
    before = copy.deepcopy(BASE)
    apply_delta(BASE, delta())
    assert BASE == before


def test_a_structural_error_is_returned_and_nothing_is_merged():
    bad = "stages:\n  lint:\n    entity: lead\n    needs: [ghost]\n    produces: [x]\n    metrics: [rework]\n"
    merged, errs, _ = apply_delta(BASE, delta(bad))
    assert merged is None and has(errs, "ghost")


def test_a_delta_with_no_change_hypothesis_fails_in_strict_mode():
    merged, errs, _ = apply_delta(BASE, f"---\n{LINT}---\n")
    assert has(errs, "change")


def test_a_protected_change_is_flagged_and_rejected_unless_ratified():
    protected_delta = delta("kpis:\n  flow:\n    owner: lead\n")
    merged, errs, protected = apply_delta(BASE, protected_delta)
    assert protected is True and errs != [] and merged is None
    merged, errs, protected = apply_delta(BASE, protected_delta, ratified=True)
    assert protected is True and errs == [] and merged["kpis"]["flow"]["owner"] == "lead"


def test_ratification_does_not_excuse_a_structural_error():
    bad = "kpis:\n  flow:\n    owner: lead\nstages:\n  lint:\n    needs: [ghost]\n"
    merged, errs, _ = apply_delta(BASE, delta(bad), ratified=True)
    assert merged is None and has(errs, "ghost")


def test_a_non_strict_delta_needs_no_change_hypothesis():
    merged, errs, _ = apply_delta(BASE, f"---\n{LINT}---\n", strict=False)
    assert errs == [] and "lint" in merged["stages"]


def test_an_empty_delta_is_a_no_op_with_no_hypothesis_needed():
    merged, errs, protected = apply_delta(BASE, "---\nstages:\n---\n")
    assert errs == [] and merged == BASE and protected is False


NO_LOOPS = MET.replace(MET[MET.index("loops:"):MET.index("stages:")], "")


def test_a_delta_that_adds_an_empty_map_still_needs_a_change_hypothesis():
    base, _ = parse_procedure(NO_LOOPS, "<base>")
    merged, errs, _ = apply_delta(base, "---\nloops:\n---\n")
    assert merged is None and has(errs, "change")


def test_a_delta_that_changes_nothing_needs_no_hypothesis():
    base, _ = parse_procedure(MET, "<base>")
    merged, errs, _ = apply_delta(base, "---\nstages:\n  align:\n    entity: pm\n---\n")
    assert errs == [] and merged == base
