import pytest
from procedure_testkit import has, main, strict_validate_layers as layers

BASE = """---
entities:
  pm:
    escalates-to: owner
  dev:
    escalates-to: pm
kpis:
  flow:
    owner: owner
    metrics: [m]
loops:
  fix:
    stages: [build, gate]
    exit:
      kind: approval
    bound: 3
    on-exhausted: owner
stages:
  build:
    entity: dev
    produces: [change]
    metrics: [m]
  gate:
    floor: true
    entity: pm
    needs: [build]
    consumes: [change]
    produces: [approval]
    metrics: [m]
  release:
    entity: pm
    needs: [gate]
    consumes: [approval]
    metrics: [m]
---
"""
CHANGE = "change:\n  reason: tested\n  metrics: [m]\n  direction: down\n  window: 5 runs\n"


def delta(body):
    return f"---\n{CHANGE}{body}---\n"


DISABLE_AND_REPLACE = (
    "stages:\n  release:\n    disabled: true\n"
    "  ship:\n    entity: pm\n    needs: [build]\n    consumes: [change]\n    metrics: [m]\n"
)
DISABLE_FLOOR = (
    "stages:\n  gate:\n    disabled: true\n"
    "  release:\n    needs: [build]\n    consumes: [change]\n"
    "loops:\n  fix:\n    stages: [build]\n    exit:\n      kind: change\n"
)
KPI_OWNER = "kpis:\n  flow:\n    owner: dev\n"
LOOP_GONE = "loops:\n  fix:\n    disabled: true\n"


def test_a_delta_cannot_remove_a_stage_that_waits_on_a_floor_stage():
    assert has(layers(BASE, delta(DISABLE_AND_REPLACE)), "floor")


def test_a_delta_may_remove_a_stage_that_does_not_wait_on_a_floor_stage():
    body = "stages:\n  build:\n    metrics: [m]\n  extra:\n    entity: dev\n    metrics: [m]\n"
    assert layers(BASE, delta(body)) == []
    assert layers(BASE, delta("stages:\n  extra:\n    disabled: true\n")) != []  # unknown stage


@pytest.mark.parametrize("body", [DISABLE_AND_REPLACE, DISABLE_FLOOR, KPI_OWNER, LOOP_GONE])
def test_a_ratified_change_to_the_protected_set_passes(body):
    assert layers(BASE, delta(body), ratified=True) == []


@pytest.mark.parametrize("body", [DISABLE_AND_REPLACE, DISABLE_FLOOR, KPI_OWNER, LOOP_GONE])
def test_the_same_change_is_rejected_when_not_ratified(body):
    assert layers(BASE, delta(body)) != []


def test_ratification_does_not_excuse_a_structural_error():
    cycle = "stages:\n  build:\n    needs: [release]\n"
    assert has(layers(BASE, delta(cycle), ratified=True), "cycle")


def test_ratification_does_not_excuse_a_missing_change_hypothesis():
    assert has(layers(BASE, f"---\n{DISABLE_FLOOR}---\n", ratified=True), "change")


def test_the_cli_has_no_flag_that_ratifies(tmp_path):
    base = tmp_path / "b.md"
    base.write_text(BASE)
    d = tmp_path / "d.md"
    d.write_text(delta(DISABLE_FLOOR))
    with pytest.raises(SystemExit):
        main(["--base", str(base), "--delta", str(d), "--ratified"])


def test_a_change_must_give_a_reason_the_owner_can_judge():
    body = "stages:\n  release:\n    metrics: [m]\n"
    no_reason = "---\nchange:\n  metrics: [m]\n  direction: down\n  window: 5 runs\n" + body + "---\n"
    assert has(layers(BASE, no_reason), "reason")
    empty = no_reason.replace("change:\n", "change:\n  reason:\n")
    assert has(layers(BASE, empty), "reason")
    assert layers(BASE, delta(body)) == []
