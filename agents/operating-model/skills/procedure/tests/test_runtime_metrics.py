import json

import pytest
from procedure_testkit import step
from runtime import COLLECTORS, collector, observed_rates
from metrics_fixtures import MET, amended, approve, item_of, propose, run_with, verify
from runtime_fixtures import SWE, dos, done, failed, fresh, of, run, started

NOTE = {"verdict": "note://defects"}


def counters(state, version=None):
    return state["metrics"][str(version or state["version"])]


def at_review(text=MET):
    state, _ = started(text)
    state, _ = run(state, done("align"), done("spec"), done("build"))
    return state


def test_every_finished_stage_is_counted():
    state, _ = started(MET)
    state, _ = run(state, done("align"), done("spec"))
    assert counters(state)["stages-done"] == 2


def test_a_refused_stage_result_is_not_counted_as_done():
    state, _ = started(MET)
    state, _ = run(state, done("align", {}))
    assert counters(state)["stages-done"] == 0


def test_rework_counts_each_stage_a_loop_round_makes_run_again():
    state = at_review()
    state, _ = run(state, failed("review", NOTE))
    assert counters(state)["rework"] == 2 and counters(state)["rounds"] == 1


def test_rework_counts_the_stages_an_on_fail_retry_runs_again():
    text = MET.replace(
        "loops:\n  fix:\n    stages: [build, review]\n    exit:\n      kind: verdict\n    bound: 3\n    on-exhausted: lead\n    carries: verdict\n",
        "",
    ).replace("    entity: worker\n    needs: [spec]", "    entity: worker\n    on-fail:\n      to: build\n      bound: 2 rounds\n    needs: [spec]")
    state, _ = started(text)
    state, _ = run(state, done("align"), done("spec"), failed("build"))
    assert counters(state)["rework"] == 1


def test_every_escalation_is_counted():
    state, _ = started(MET)
    state, _ = run(state, {"type": "advice-requested", "from": "worker", "question": "q"})
    state, _ = run(state, failed("align"))
    assert counters(state)["escalations"] == 2


def test_every_refused_event_is_counted():
    state, _ = started(MET)
    state, _ = run(state, {"type": "teleport"}, "not an event", done("align", {}))
    assert counters(state)["refusals"] == 3


def test_an_agent_cannot_write_a_metric():
    state, _ = started(MET)
    before = dict(counters(state))
    state, acts = run(state, {"type": "metric-sample", "name": "rework", "value": -99})
    assert dos(acts[0]) == ["error"] and counters(state)["rework"] == before["rework"]
    state, _ = run(state, {"type": "stage-done", "stage": "align", "locators": {"brief": "doc://b"}, "metrics": {"rework": -5}})
    assert counters(state)["rework"] == 0 and counters(state)["stages-done"] == 1


def test_a_rate_is_the_count_per_finished_stage():
    state = at_review()
    state, _ = run(state, failed("review", NOTE))
    assert observed_rates(state)["rework"] == pytest.approx(2 / 3)
    assert observed_rates(state)["escalations"] == 0


def test_a_rate_with_no_finished_stage_is_the_raw_count_not_a_division_by_zero():
    state, _ = started(MET)
    state, _ = run(state, {"type": "teleport"})
    assert observed_rates(state)["refusals"] == 1


def test_counters_start_again_under_each_snapshot():
    state, acts = amended()
    assert counters(state, 1)["stages-done"] == 1 and counters(state, 2)["stages-done"] == 0
    state, _ = run_with({"type": "stage-done", "stage": "spec", "locators": {"item": "issue://1"}}, state=state)
    assert counters(state, 2)["stages-done"] == 1 and counters(state, 1)["stages-done"] == 1


def test_a_run_says_which_declared_metrics_nothing_observes():
    state, acts = started(SWE)
    unobserved = of(acts, "metrics-unobserved")
    assert unobserved and unobserved[0]["metrics"] == ["m"]


def test_a_run_whose_metrics_are_all_observed_reports_nothing_missing():
    state, acts = started(MET)
    assert not of(acts, "metrics-unobserved")


def test_trusted_code_can_register_a_collector_for_a_custom_metric():
    @collector("defects")
    def defects(c):
        return c.get("rounds", 0) * 10

    try:
        text = MET.replace(
            "  align:\n    entity: pm\n    produces: [brief]\n    metrics: [rework]",
            "  align:\n    entity: pm\n    produces: [brief]\n    metrics: [rework, defects]",
        ).replace("    metrics: [rework]\nloops:", "    metrics: [rework, defects]\nloops:")
        state, acts = started(text)
        assert not of(acts, "metrics-unobserved") and "defects" in observed_rates(state)
    finally:
        COLLECTORS.pop("defects", None)


def test_the_metrics_survive_json():
    state = at_review()
    state, _ = run(state, failed("review", NOTE))
    assert json.loads(json.dumps(state))["metrics"] == state["metrics"]


def test_a_hostile_event_cannot_make_a_counter_go_negative_or_non_integer():
    state, _ = started(MET)
    state, _ = run(state, {"type": "stage-done", "stage": "align", "locators": {"brief": "x"}, "count": -1})
    assert all(type(v) is int and v >= 0 for v in counters(state).values())


def test_a_proposal_to_the_owner_is_not_counted_as_an_escalation():
    state, acts = run_with(propose())
    assert counters(state)["escalations"] == 0
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, state=state)
    assert counters(state)["escalations"] == 1
