import json
import math

import pytest
from procedure_testkit import replay, step
from metrics_fixtures import MET, NOTE, approve, delta, item_of, propose, regressed_run, run_with, v2, verify
from runtime_fixtures import dos, done, failed, fresh, of, started

LINT_OFF = "stages:\n  lint:\n    disabled: true\n"
DOCS = "stages:\n  docs:\n    entity: lead\n    needs: [spec]\n    consumes: [item]\n    produces: [notes]\n    metrics: [rework]\n"


def rollback_item(acts):
    return next(a["item"] for a in acts if a["do"] == "escalate")


def pm_sure(item):
    return {"type": "advice-given", "item": item, "by": "pm", "answer": "sure: roll back"}


def finish_v2_stages(state):
    state, _ = run_with(done("lint", {"lint-report": "l://1"}), done("review"), state=state)
    return state


# ---- a rollback must still target the current, regressed change


def test_a_rollback_for_a_change_that_was_since_replaced_is_closed_not_applied():
    state, acts = regressed_run()
    item = rollback_item(acts)
    state, a = run_with(propose(delta(LINT_OFF, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a[0])), state=state)
    state = finish_v2_stages(state)
    assert state["version"] == 3
    state, acts = run_with(pm_sure(item), state=state)
    assert [x["do"] for x in acts[0]] == ["advice-resolved", "rollback-stale"] or "rollback-stale" in [x["do"] for x in acts[0]]
    assert state["version"] == 3 and state["pending"] == []
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "stale"


def test_an_owner_decision_to_roll_back_a_replaced_change_is_closed_the_same_way():
    state, acts = regressed_run()
    item = rollback_item(acts)
    state, _ = run_with({"type": "advice-given", "item": item, "by": "pm", "answer": "unsure: you decide"}, state=state)
    state, a = run_with(propose(delta(LINT_OFF, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a[0])), state=state)
    state = finish_v2_stages(state)
    state, acts = run_with(approve(item, "rollback"), state=state)
    assert "rollback-stale" in [x["do"] for x in acts[0]] and state["version"] == 3


# ---- nothing waiting for a stage boundary is lost


def test_a_second_approval_is_not_silently_dropped_it_is_reported_as_failed():
    state = v2(window="9 stages")
    state, a1 = run_with(propose(delta(DOCS, window="2 stages")), state=state)
    state, a2 = run_with(propose(delta(LINT_OFF, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a1[0])), approve(item_of(a2[0])), state=state)
    assert len(state["pending"]) == 2
    state, acts = run_with(done("spec"), state=state)
    kinds = [x["do"] for x in acts[0]]
    assert "snapshot-applied" in kinds and "amendment-failed" in kinds
    assert state["version"] == 3 and state["pending"] == []


def test_a_rollback_and_an_approved_amendment_both_get_a_visible_outcome():
    state, acts = regressed_run()
    item = rollback_item(acts)
    state, a = run_with(propose(delta(LINT_OFF, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a[0])), pm_sure(item), state=state)
    assert [p["kind"] for p in state["pending"]] == ["amendment", "rollback"]
    state, acts = run_with(done("lint", {"lint-report": "l://1"}), done("review"), state=state)
    kinds = [x["do"] for x in acts[1]]
    assert "snapshot-applied" in kinds and "rollback-stale" in kinds


def test_a_deferred_safety_rollback_is_recorded_as_rolled_back_only_when_it_applies():
    state = v2(window="2 stages", policy={"safety-metrics": ["escalations"]})
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, done("spec"), state=state)
    state, acts = run_with(done("build"), state=state)
    assert state["version"] == 3  # nothing else was running, so it applied at once
    state = v2(window="3 stages", policy={"safety-metrics": ["escalations"]})
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, done("spec"), done("build"), state=state)
    state, _ = run_with(failed("review", NOTE), state=state)
    state, acts = run_with(done("build"), state=state)
    assert state["snapshots"][1]["outcome"] in ("rolled-back", "regressed")
    if state["pending"]:
        assert state["snapshots"][1]["outcome"] == "regressed"


# ---- replay reproduces the run, refused events included


def core(state):
    return {k: state[k] for k in ("status", "version", "stages", "pending", "metrics")} | {
        "outcomes": [s["outcome"] for s in state["snapshots"]], "items": state.get("items")}


def test_replaying_the_log_gives_the_same_state_even_when_events_were_refused():
    policy = {"safety-metrics": ["refusals"]}
    state = v2(window="2 stages", policy=policy)
    state, _ = run_with({"type": "teleport"}, state=state)
    state, _ = run_with(done("spec"), done("build"), state=state)
    assert state["version"] == 3
    again, _ = replay(MET, state["log"], verify_owner=verify, policy=policy)
    assert core(again) == core(state)


def test_a_refused_event_is_in_the_log_so_the_run_can_be_replayed():
    state, _ = started(MET)
    before = len(state["log"])
    state, _ = run_with({"type": "teleport"}, state=state)
    assert len(state["log"]) == before + 1 and state["log"][-1]["type"] == "teleport"


def test_an_event_that_cannot_be_stored_is_logged_as_an_unreadable_placeholder():
    state, _ = started(MET)
    state, _ = run_with(10**5000, {"type": "x", "deep": [[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]}, state=state)
    assert [e["type"] for e in state["log"][-2:]] == ["unreadable-event", "unreadable-event"]
    again, _ = replay(MET, state["log"], verify_owner=verify)
    assert again["metrics"] == state["metrics"]


def test_a_refused_forged_owner_decision_replays_as_refused():
    state, acts = run_with(propose())
    state, _ = run_with({"type": "owner-decided", "item": item_of(acts[0]), "decision": "approve", "signature": "forged"}, state=state)
    again, _ = replay(MET, state["log"], verify_owner=verify)
    assert core(again) == core(state) and again["version"] == 1


# ---- a blocked run cannot be wedged by a change to the stage it waits on


def test_removing_the_stage_a_blocked_run_waits_on_does_not_wedge_the_run():
    state = v2(window="9 stages")
    state, _ = run_with(done("spec"), done("build"), done("review"), done("integrate", {"merged": "m://1"}), state=state)
    state, acts = run_with(failed("lint"), state=state)
    item = rollback_item(acts)
    state, a = run_with(propose(delta(LINT_OFF, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a[0])), state=state)
    assert "lint" not in state["stages"]
    state, acts = run_with({"type": "advice-given", "item": item, "by": "pm", "answer": "sure: carry on"}, state=state)
    assert "error" not in [x["do"] for x in acts[0]] and state["status"] == "done"


# ---- what the owner approves is what applies


AUDIT = "stages:\n  audit:\n    entity: lead\n    needs: [spec]\n    consumes: [item]\n    produces: [report]\n    metrics: [rework]\n"


def test_an_approved_proposal_made_against_an_older_procedure_is_reported_as_failed():
    state, a1 = run_with(propose(delta(DOCS, window="2 stages")))
    state, a2 = run_with(propose(delta(AUDIT, window="2 stages")), state=state)
    state, _ = run_with(approve(item_of(a1[0])), done("align"), state=state)
    assert state["version"] == 2 and "docs" in state["proc"]["stages"]
    state, _ = run_with(approve(item_of(a2[0])), state=state)
    state, acts = run_with(done("spec"), state=state)
    assert any(a["do"] == "amendment-failed" for a in acts[0])
    assert state["version"] == 2 and "audit" not in state["proc"]["stages"]


def test_the_owner_verifier_sees_a_digest_of_what_is_being_approved():
    seen = []

    def watch(event):
        seen.append(event.get("item_digest"))
        return verify(event)

    state, a1 = run_with(propose(delta(DOCS, window="2 stages")))
    state, _ = run_with(propose(delta(DOCS.replace("docs", "docs2"), window="3 stages")), state=state)
    other = next(i for i in state["items"] if i["id"] != item_of(a1[0]))["id"]
    from procedure_testkit import step as raw
    for item in (item_of(a1[0]), other):
        raw(state, approve(item), verify_owner=watch)
    assert all(isinstance(d, str) and len(d) == 64 for d in seen) and seen[0] != seen[1]


def test_a_decision_is_refused_once_the_run_is_done_or_halted():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    state["status"] = "done"
    assert dos(run_with(approve(item), state=state)[1][0]) == ["error"]
    state["status"] = "halted"
    assert dos(run_with(approve(item), state=state)[1][0]) == ["error"]


# ---- a stage whose outputs changed is run again


def test_a_finished_stage_whose_produced_kinds_changed_is_run_again():
    state, acts = run_with(propose(delta("stages:\n  build:\n    produces: [change, notes]\n", window="2 stages")))
    item = item_of(acts[0])
    state, _ = run_with(done("align"), done("spec"), done("build"), state=state)
    state, _ = run_with(approve(item), state=state)
    assert state["version"] == 1 and state["pending"]
    state, acts = run_with(done("review"), state=state)
    assert state["version"] == 2
    assert state["stages"]["build"]["status"] == "running" and state["stages"]["review"]["status"] == "pending"
    assert any(a["do"] == "start-stage" and a["stage"] == "build" for a in acts[0])


# ---- inputs that should not be accepted


def test_a_proposal_with_a_change_map_that_names_nothing_is_refused_even_through_an_empty_map():
    base = MET.replace(MET[MET.index("loops:"):MET.index("stages:")], "")
    state, _ = started(base)
    state, acts = run_with(propose("---\nchange:\n  window: 1 stages\nloops:\n---\n"), state=state)
    assert dos(acts[0]) == ["error"]


def test_a_base_procedure_that_carries_a_change_map_does_not_keep_it_in_the_frozen_state():
    text = MET.replace("stages:\n  align", "change:\n  reason: left over\nstages:\n  align", 1)
    assert "change" not in fresh(text)["proc"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_a_threshold_must_be_a_finite_number(bad):
    with pytest.raises(ValueError, match="regression-threshold"):
        fresh(MET, policy={"regression-threshold": bad})


def test_a_safety_metric_nothing_observes_is_refused_so_a_typo_cannot_disable_it():
    with pytest.raises(ValueError, match="escalatons"):
        fresh(MET, policy={"safety-metrics": ["escalatons"]})


def test_a_window_may_not_be_absurdly_long():
    assert dos(run_with(propose(delta(window="999 stages")))[1][0]) == ["notify-owner"]
    assert dos(run_with(propose(delta(window="1000 stages")))[1][0]) == ["error"]
