from procedure_testkit import delta, has, strict_validate_layers as layers, strict_validate_text as check

BASE = """---
entities:
  pm:
    escalates-to: owner
    may-spawn: [lead]
  lead:
    escalates-to: pm
    may-spawn: [worker]
  worker:
    escalates-to: lead
kpis:
  flow:
    owner: owner
    metrics: [m]
loops:
  fix:
    stages: [build, review]
    exit:
      kind: findings
    bound: 3
    on-exhausted: owner
stages:
  build:
    entity: worker
    produces: [change]
    metrics: [m]
  review:
    entity: lead
    needs: [build]
    consumes: [change]
    produces: [findings]
    metrics: [m]
---
"""
def test_the_base_is_valid():
    assert check(BASE) == []


def test_a_delta_cannot_reroute_an_existing_entity_up_the_ladder():
    assert has(layers(BASE, delta("entities:\n  worker:\n    escalates-to: owner\n")), "protected")


def test_a_delta_cannot_move_a_rung_to_change_who_may_spawn():
    body = "entities:\n  pm:\n    escalates-to: worker\n  worker:\n    escalates-to: owner\n"
    assert has(layers(BASE, delta(body)), "protected")


def test_a_delta_can_add_an_entity_below_an_existing_one():
    body = "entities:\n  helper:\n    escalates-to: worker\n"
    assert layers(BASE, delta(body)) == []


def test_a_delta_cannot_remove_a_loop():
    assert has(layers(BASE, delta("loops:\n  fix:\n    disabled: true\n")), "protected")


def test_a_delta_cannot_redirect_where_a_loop_escalates():
    assert has(layers(BASE, delta("loops:\n  fix:\n    on-exhausted: worker\n")), "protected")


def test_a_delta_cannot_raise_a_loop_bound_but_can_lower_it():
    assert has(layers(BASE, delta("loops:\n  fix:\n    bound: 999\n")), "bound")
    assert layers(BASE, delta("loops:\n  fix:\n    bound: 2\n")) == []


def test_a_delta_cannot_reassign_or_remove_a_kpi():
    assert has(layers(BASE, delta("kpis:\n  flow:\n    owner: worker\n")), "protected")
    assert has(layers(BASE, delta("kpis:\n  flow:\n    disabled: true\n")), "protected")


def test_a_delta_can_add_a_kpi_for_a_new_metric():
    body = (
        "kpis:\n  quality:\n    owner: owner\n    metrics: [defects]\n"
        "stages:\n  review:\n    metrics: [m, defects]\n"
    )
    change = "change:\n  reason: tested\n  metrics: [defects]\n  direction: down\n  window: 3 runs\n"
    assert layers(BASE, f"---\n{change}{body}---\n") == []


def test_a_non_ascii_digit_bound_is_an_error_not_a_crash():
    assert has(check(BASE.replace("bound: 3", "bound: \u00b2")), "bound")


def test_mixed_bool_and_text_metrics_are_an_error_not_a_crash():
    text = "---\nkpis:\n  k:\n    owner: owner\n    metrics: [z]\nstages:\n  a:\n    metrics: [true, x]\n---\n"
    assert has(check(text), "metric")
