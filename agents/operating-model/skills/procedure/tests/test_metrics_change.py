from procedure_testkit import (
    FIXTURES,
    has,
    main,
    strict_validate_layers as layers,
    strict_validate_text as check,
    validate_text,
)

GOOD = """---
name: t
entities:
  pm:
    role: project-manager
    escalates-to: owner
kpis:
  flow:
    owner: pm
    metrics: [lead-time, rework]
stages:
  build:
    entity: pm
    produces: [change]
    metrics: [lead-time]
  review:
    entity: pm
    needs: [build]
    consumes: [change]
    produces: [findings]
    metrics: [rework]
---
"""


def test_a_procedure_with_linked_metrics_passes_strict():
    assert check(GOOD) == []


def test_the_campaign_ops_fixture_passes_strict():
    assert check((FIXTURES / "campaign-ops.md").read_text()) == []


def test_a_stage_without_metrics_fails():
    text = GOOD.replace("    metrics: [lead-time]\n", "")
    assert has(check(text), "metric")


def test_a_stage_with_an_empty_metric_list_fails():
    assert has(check(GOOD.replace("metrics: [lead-time]", "metrics: []")), "metric")


def test_a_metric_no_kpi_links_fails():
    text = GOOD.replace("metrics: [lead-time, rework]", "metrics: [rework]")
    assert has(check(text), "lead-time")


def test_a_kpi_naming_an_undeclared_metric_fails():
    text = GOOD.replace("metrics: [lead-time, rework]", "metrics: [lead-time, rework, ghost]")
    assert has(check(text), "ghost")


def test_a_kpi_needs_an_owner_that_is_an_entity_or_owner():
    assert check(GOOD.replace("owner: pm\n    metrics", "owner: owner\n    metrics")) == []
    assert has(check(GOOD.replace("owner: pm\n    metrics", "owner: ghost\n    metrics")), "owner")
    assert has(check(GOOD.replace("    owner: pm\n    metrics", "    metrics")), "owner")


def test_a_kpi_needs_a_non_empty_metric_list():
    assert has(check(GOOD.replace("metrics: [lead-time, rework]", "metrics: []")), "kpi")


def test_structure_checks_do_not_require_metrics_when_not_strict():
    assert validate_text("---\nstages:\n  a:\n    produces: [x]\n---\n") == []


def test_metrics_are_required_when_strict_by_default():
    assert has(check("---\nstages:\n  a:\n    produces: [x]\n---\n"), "metric")


CHANGE = "change:\n  reason: tested\n  metrics: [rework]\n  direction: down\n  window: 5 runs\n"


def delta(body, change=CHANGE):
    return f"---\n{change}{body}---\n"


ADD_STAGE = (
    "stages:\n  scan:\n    entity: pm\n    needs: [build]\n    consumes: [change]\n"
    "    produces: [scan-report]\n    metrics: [lead-time]\n"
)


def test_a_delta_with_a_change_hypothesis_passes():
    assert layers(GOOD, delta(ADD_STAGE)) == []


def test_a_delta_without_a_change_hypothesis_fails():
    assert has(layers(GOOD, delta(ADD_STAGE, change="")), "change")


def test_a_change_must_name_metrics_that_exist():
    bad = "change:\n  reason: tested\n  metrics: [ghost]\n  direction: down\n  window: 5 runs\n"
    assert has(layers(GOOD, delta(ADD_STAGE, bad)), "ghost")


def test_a_change_needs_a_direction_up_or_down():
    bad = "change:\n  reason: tested\n  metrics: [rework]\n  direction: sideways\n  window: 5 runs\n"
    assert has(layers(GOOD, delta(ADD_STAGE, bad)), "direction")


def test_a_change_needs_an_observation_window():
    bad = "change:\n  reason: tested\n  metrics: [rework]\n  direction: down\n"
    assert has(layers(GOOD, delta(ADD_STAGE, bad)), "window")


def test_a_delta_cannot_strip_the_last_metric_from_a_stage():
    body = "stages:\n  review:\n    metrics: []\n"
    assert has(layers(GOOD, delta(body)), "metric")


def test_a_delta_may_swap_a_metric_when_the_kpi_follows():
    body = (
        "kpis:\n  flow:\n    metrics: [lead-time, defects]\n"
        "stages:\n  review:\n    metrics: [defects]\n"
    )
    change = "change:\n  reason: tested\n  metrics: [defects]\n  direction: down\n  window: 3 runs\n"
    assert layers(GOOD, delta(body, change)) == []


def test_an_empty_delta_needs_no_change_hypothesis():
    assert layers(GOOD, "---\nstages:\n---\n") == []


def test_the_cli_is_strict_and_has_no_opt_out(tmp_path, capsys):
    f = tmp_path / "p.md"
    f.write_text("---\nstages:\n  a:\n    produces: [x]\n---\n")
    assert main([str(f)]) == 1
    assert "metric" in capsys.readouterr().err
