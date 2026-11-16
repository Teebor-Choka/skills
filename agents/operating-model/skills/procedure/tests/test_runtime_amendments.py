import json

import pytest
from procedure_testkit import step
from metrics_fixtures import LINT, MET, approve, change, delta, item_of, propose, run_with, verify
from runtime_fixtures import dos, done, fresh, of, started

PROTECTED = delta("kpis:\n  flow:\n    owner: lead\n")


def test_a_new_run_starts_at_snapshot_one_holding_the_frozen_procedure():
    state = fresh(MET)
    assert state["version"] == 1 and len(state["snapshots"]) == 1
    assert state["snapshots"][0]["version"] == 1 and state["snapshots"][0]["proc"] == state["proc"]
    assert state["snapshots"][0]["change"] is None


def test_a_proposal_goes_to_the_owner_with_the_reasoning_and_applies_nothing():
    state, acts = run_with(propose(reason="fewer defects"))
    ask = acts[0][0]
    assert ask["do"] == "notify-owner" and ask["default-if-silent"] == "wait"
    assert ask["change"]["reason"] == "fewer defects" and ask["change"]["metrics"] == ["rework"]
    assert ask["change"]["direction"] == "down" and ask["change"]["window"] == "2 stages"
    assert state["version"] == 1 and "lint" not in state["proc"]["stages"]


def test_the_run_keeps_going_on_the_old_procedure_while_the_owner_decides():
    state, _ = run_with(propose())
    state, acts = run_with(done("align"), state=state)
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["spec"] and state["version"] == 1


def test_a_proposal_says_whether_it_touches_the_protected_set():
    _, acts = run_with(propose(PROTECTED))
    assert acts[0][0]["protected"] is True
    _, acts = run_with(propose())
    assert acts[0][0]["protected"] is False


def test_a_proposal_that_fails_validation_is_refused_with_the_errors():
    bad = delta("stages:\n  lint:\n    needs: [ghost]\n    entity: lead\n    metrics: [rework]\n")
    state, acts = run_with(propose(bad))
    assert dos(acts[0]) == ["error"] and "ghost" in acts[0][0]["reason"] and not state.get("items")


def test_a_proposal_without_a_change_hypothesis_is_refused():
    state, acts = run_with(propose(f"---\n{LINT}---\n"))
    assert dos(acts[0]) == ["error"] and "change" in acts[0][0]["reason"]


def test_a_proposal_naming_a_metric_nothing_observes_is_refused():
    state, acts = run_with(propose(delta(**{"metrics": "defects"})))
    assert dos(acts[0]) == ["error"] and "defects" in acts[0][0]["reason"]


@pytest.mark.parametrize("window", ["5 runs", "soon", "3", "0 stages", "-2 stages", "2 stages and more"])
def test_the_window_must_be_a_count_of_stages(window):
    state, acts = run_with(propose(delta(window=window)))
    assert dos(acts[0]) == ["error"] and "window" in acts[0][0]["reason"]


def test_only_an_entity_may_propose_and_only_on_a_live_run():
    state, acts = run_with(propose(by="ghost"))
    assert dos(acts[0]) == ["error"]
    assert dos(step(fresh(MET), propose())[1]) == ["error"]


def test_an_owner_approval_applies_the_change_as_the_next_snapshot():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    state, acts = run_with(approve(item), state=state)
    assert state["version"] == 2 and "lint" in state["proc"]["stages"]
    assert {"do": "snapshot-applied", "version": 2} in acts[0] or any(a["do"] == "snapshot-applied" and a["version"] == 2 for a in acts[0])
    assert state["snapshots"][1]["change"]["reason"] == "tighten review"


def test_snapshot_history_is_append_only():
    state, acts = run_with(propose())
    before = json.dumps(state["snapshots"][0], sort_keys=True)
    state, _ = run_with(approve(item_of(acts[0])), state=state)
    assert json.dumps(state["snapshots"][0], sort_keys=True) == before and len(state["snapshots"]) == 2


def test_stages_already_done_keep_their_status_and_a_new_stage_becomes_ready():
    state, acts = run_with(propose())
    state, _ = run_with(done("align"), done("spec"), done("build"), state=state)
    state, acts = run_with(approve(item_of(acts[0])), state=state)
    assert state["stages"]["build"]["status"] == "done"
    assert any(a["do"] == "start-stage" and a["stage"] == "lint" for a in acts[0])


def test_an_approval_waits_for_a_stage_boundary_when_a_stage_is_running():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    state, acts = run_with(approve(item), state=state)
    assert state["version"] == 1 and state["pending"]["kind"] == "amendment"
    state, acts = run_with(done("align"), state=state)
    assert state["version"] == 2 and state["pending"] is None


def test_an_approval_with_no_valid_signature_applies_nothing():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    forged = {"type": "owner-decided", "item": item, "decision": "approve", "signature": "forged"}
    state, acts = run_with(forged, state=state)
    assert dos(acts[0]) == ["error"] and state["version"] == 1 and not state.get("pending")


def test_any_other_decision_closes_the_proposal_without_applying_it():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    state, acts = run_with(approve(item, "reject"), state=state)
    assert state["version"] == 1 and dos(acts[0]) == ["owner-ruled"]
    assert dos(run_with(approve(item), state=state)[1][0]) == ["error"]


def test_an_owner_approval_applies_a_protected_change():
    state, acts = run_with(propose(PROTECTED))
    state, _ = run_with(approve(item_of(acts[0])), state=state)
    assert state["proc"]["kpis"]["flow"]["owner"] == "lead"


def test_a_proposal_is_checked_against_the_current_snapshot_not_the_first():
    state, acts = run_with(propose())
    state, _ = run_with(approve(item_of(acts[0])), state=state)
    again = delta("stages:\n  lint:\n    disabled: true\n")
    state, acts = run_with(propose(again), state=state)
    assert dos(acts[0]) == ["notify-owner"]


def test_a_proposal_cannot_be_decided_by_an_entity():
    state, acts = run_with(propose())
    item = item_of(acts[0])
    for by in ("pm", "lead", "owner"):
        out = run_with({"type": "advice-given", "item": item, "by": by, "answer": "sure"}, state=state)[1][0]
        assert dos(out) == ["error"]
    assert state["version"] == 1
