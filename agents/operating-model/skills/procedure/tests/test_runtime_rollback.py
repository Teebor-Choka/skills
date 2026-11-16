import json

import pytest
from procedure_testkit import step
from runtime import observed_rates, regressed
from metrics_fixtures import (MET, NOTE, approve, delta, item_of, propose, regressed_run, run_with, v2, verify)
from runtime_fixtures import dos, done, failed, fresh, of, started


def verdicts(acts):
    return [a for a in acts if a["do"] in ("change-confirmed", "change-regressed")]


# ---- the comparison itself


@pytest.mark.parametrize("observed, baseline, direction, threshold, worse", [
    (0.5, 0.0, "down", 0.1, True),       # from nothing to something is worse
    (0.0, 0.0, "down", 0.1, False),
    (0.11, 0.1, "down", 0.1, False),     # within the tolerance
    (0.12, 0.1, "down", 0.1, True),
    (0.2, 0.4, "down", 0.0, False),      # it fell: better
    (0.5, 0.0, "up", 0.1, False),        # cannot fall below zero
    (0.3, 0.5, "up", 0.1, True),
    (0.46, 0.5, "up", 0.1, False),
    (0.6, 0.5, "up", 0.1, False),
])
def test_a_metric_is_worse_when_it_moves_the_wrong_way_past_the_tolerance(observed, baseline, direction, threshold, worse):
    assert regressed(observed, baseline, direction, threshold) is worse


# ---- judging a change


def test_no_verdict_comes_before_the_window_is_spent():
    state = v2(window="2 stages")
    state, acts = run_with(done("spec"), state=state)
    assert not verdicts(acts[0]) and state["snapshots"][1]["outcome"] == "pending"


def test_a_change_that_did_not_regress_is_confirmed_with_the_evidence():
    state = v2(window="2 stages")
    state, acts = run_with(done("spec"), done("build"), state=state)
    verdict = verdicts(acts[1])[0]
    assert verdict["do"] == "change-confirmed" and verdict["version"] == 2
    assert verdict["metrics"]["rework"] == {"baseline": 0.0, "observed": 0.0, "direction": "down"}
    assert state["snapshots"][1]["outcome"] == "confirmed"


def test_a_change_is_judged_once():
    state = v2(window="2 stages")
    state, acts = run_with(done("spec"), done("build"), done("lint", {"lint-report": "l://1"}), state=state)
    assert len(verdicts(acts[1])) == 1 and not verdicts(acts[2])


def test_the_baseline_is_the_rate_under_the_snapshot_before_the_change():
    state = v2()
    assert state["snapshots"][1]["baseline"]["rework"] == 0.0


# ---- a regression becomes a proposal, not a silent change


def test_a_regression_raises_a_rollback_proposal_to_the_project_manager():
    state, acts = regressed_run()
    verdict = verdicts(acts)[0]
    assert verdict["do"] == "change-regressed" and verdict["metrics"]["rework"]["observed"] > 0
    ask = next(a for a in acts if a["do"] == "escalate")
    assert ask["to"] == "pm" and ask["kind"] == "rollback" and "evidence" in ask
    assert state["version"] == 2 and state["status"] == "running"


def test_a_regression_proposal_goes_to_the_owner_when_no_entity_is_a_project_manager():
    text = MET.replace("role: project-manager", "role: coordinator")
    state, acts = run_with(propose(window="3 stages"), state=started(text)[0])
    state, _ = run_with(approve(item_of(acts[0])), done("align"), done("spec"), done("build"), failed("review", NOTE), state=state)
    state, acts = run_with(done("build"), state=state)
    assert any(a["do"] == "notify-owner" and a.get("kind") == "rollback" for a in acts[0])


def test_the_project_manager_saying_sure_rolls_back_to_the_snapshot_before_the_change():
    state, acts = regressed_run()
    item = next(a["item"] for a in acts if a["do"] == "escalate")
    state, acts = run_with({"type": "advice-given", "item": item, "by": "pm", "answer": "sure: roll back"}, state=state)
    assert state["version"] == 2 and state["pending"]["kind"] == "rollback"
    state, acts = run_with(done("lint", {"lint-report": "l://1"}), done("review"), state=state)
    assert state["version"] == 3 and "lint" not in state["proc"]["stages"]
    assert state["proc"] == state["snapshots"][0]["proc"]
    assert state["snapshots"][2]["change"]["rollback-of"] == 2
    assert [s["outcome"] for s in state["snapshots"]] == ["initial", "rolled-back", "rollback"]


def test_an_unsure_project_manager_passes_the_decision_to_the_owner():
    state, acts = regressed_run()
    item = next(a["item"] for a in acts if a["do"] == "escalate")
    state, acts = run_with({"type": "advice-given", "item": item, "by": "pm", "answer": "unsure: costs me a week"}, state=state)
    assert dos(acts[0]) == ["notify-owner"] and acts[0][0]["default-if-silent"] == "wait"
    assert state["version"] == 2


def at_owner():
    state, acts = regressed_run()
    item = next(a["item"] for a in acts if a["do"] == "escalate")
    state, _ = run_with({"type": "advice-given", "item": item, "by": "pm", "answer": "unsure: your call"}, state=state)
    return state, item


def test_an_owner_decision_of_rollback_applies_it_at_the_next_boundary():
    state, item = at_owner()
    state, _ = run_with(approve(item, "rollback"), state=state)
    state, _ = run_with(done("lint", {"lint-report": "l://1"}), done("review"), state=state)
    assert state["version"] == 3 and state["snapshots"][1]["outcome"] == "rolled-back"


def test_an_owner_decision_of_keep_leaves_the_change_in_place():
    state, item = at_owner()
    state, acts = run_with(approve(item, "keep"), state=state)
    assert state["version"] == 2 and state["snapshots"][1]["outcome"] == "kept" and not state["pending"]


def test_an_owner_decision_on_a_rollback_must_be_rollback_or_keep():
    state, item = at_owner()
    assert dos(run_with(approve(item, "maybe"), state=state)[1][0]) == ["error"]


def test_an_unsigned_decision_cannot_roll_anything_back():
    state, item = at_owner()
    forged = {"type": "owner-decided", "item": item, "decision": "rollback", "signature": "x"}
    state, acts = run_with(forged, state=state)
    assert dos(acts[0]) == ["error"] and not state["pending"]


def test_the_proposal_cannot_be_answered_by_an_entity_that_does_not_hold_it():
    state, acts = regressed_run()
    item = next(a["item"] for a in acts if a["do"] == "escalate")
    assert dos(run_with({"type": "advice-given", "item": item, "by": "lead", "answer": "sure"}, state=state)[1][0]) == ["error"]


# ---- safety metrics roll back at once


def test_a_safety_metric_that_regresses_rolls_the_change_back_without_asking():
    state = v2(window="2 stages", policy={"safety-metrics": ["escalations"]})
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, state=state)
    state, acts = run_with(done("spec"), done("build"), state=state)
    verdict = verdicts(acts[1])[0]
    assert verdict["do"] == "change-regressed" and verdict["auto"] is True
    assert state["version"] == 3 and "lint" not in state["proc"]["stages"]
    assert any(a["do"] == "inform-owner" for a in acts[1]) and not any(a["do"] == "escalate" and a.get("kind") == "rollback" for a in acts[1])


def test_with_no_safety_metrics_named_nothing_rolls_back_on_its_own():
    state = v2(window="2 stages")
    state, _ = run_with({"type": "teleport"}, {"type": "teleport"}, {"type": "teleport"}, state=state)
    state, acts = run_with(done("spec"), done("build"), state=state)
    assert state["version"] == 2 and verdicts(acts[1])[0]["do"] == "change-confirmed"


def test_a_threshold_lets_a_small_change_in_a_metric_pass():
    with pytest.raises(ValueError, match="regression-threshold"):
        fresh(MET, policy={"regression-threshold": -1})
    for bad in (True, "0.1", None, [0.1]):
        with pytest.raises(ValueError, match="regression-threshold"):
            fresh(MET, policy={"regression-threshold": bad})


def test_safety_metrics_must_be_a_list_of_names():
    for bad in ("escalations", [1], {"a": 1}, None):
        with pytest.raises(ValueError, match="safety-metrics"):
            fresh(MET, policy={"safety-metrics": bad})


# ---- the edges


def test_a_change_replaced_before_its_window_ends_is_not_judged():
    state = v2(window="3 stages")
    state, acts = run_with(propose(delta("stages:\n  lint:\n    disabled: true\n", window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(acts[0])), done("spec"), state=state)
    assert state["version"] == 3 and state["snapshots"][1]["outcome"] == "superseded"


def test_a_rollback_snapshot_is_not_itself_judged():
    state = v2(window="2 stages", policy={"safety-metrics": ["escalations"]})
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, state=state)
    state, _ = run_with(done("spec"), done("build"), state=state)
    state, acts = run_with(done("review"), state=state)
    assert state["version"] == 3 and not verdicts(acts[0])


def test_the_iteration_report_records_each_snapshot_its_change_and_its_outcome():
    from runtime import iteration_report
    state = v2(window="2 stages")
    state, _ = run_with(done("spec"), done("build"), state=state)
    report = iteration_report(state)
    assert [r["version"] for r in report] == [1, 2]
    assert report[1]["change"]["reason"] == "tighten review" and report[1]["outcome"] == "confirmed"
    assert report[1]["stages_done"] == 2 and report[1]["observed"]["rework"] == 0.0
    assert json.loads(json.dumps(report)) == report


def test_a_run_with_amendments_and_a_rollback_replays_exactly():
    from procedure_testkit import replay
    state, _ = regressed_run()
    item = state["items"][-1]["id"]
    events = state["log"] + [
        {"type": "advice-given", "item": item, "by": "pm", "answer": "sure: back"},
        done("lint", {"lint-report": "l://1"}),
        done("review"),
    ]
    first = replay(MET, events, verify_owner=verify, policy={})
    second = replay(MET, events, verify_owner=verify, policy={})
    assert first == second and first[0]["version"] == 3
