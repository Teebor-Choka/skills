import hashlib
import hmac
import json

import pytest
from runtime_fixtures import SWE, dos, done, of, run, started


def advice(frm="worker", question="which library?", **kw):
    return {"type": "advice-requested", "from": frm, "question": question, **kw}


def given(item, by, answer):
    return {"type": "advice-given", "item": item, "by": by, "answer": answer}


def owner(item, decision="yes", signature="sig"):
    return {"type": "owner-decided", "item": item, "decision": decision, "signature": signature}


def spawn(by, role, why="needs help", **kw):
    return {"type": "spawn-requested", "by": by, "role": role, "why": why, **kw}


KEY = b"owner-key-the-agents-cannot-read"


def sign(item, decision):
    return hmac.new(KEY, json.dumps([item, decision]).encode(), hashlib.sha256).hexdigest()


def verifier(event):
    return hmac.compare_digest(event.get("signature", ""), sign(event["item"], event["decision"]))


def test_advice_goes_to_the_entity_above_and_the_asker_keeps_its_stage():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    assert [(a["do"], a["to"]) for a in acts[0]] == [("escalate", "lead")]
    assert state["status"] == "running"


def test_a_sure_answer_ends_the_escalation():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    state, acts = run(state, given(item, "lead", "sure: use stdlib"))
    assert dos(acts[0]) == ["advice-resolved"] and acts[0][0]["by"] == "lead"
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "advice-ruled"


def test_an_unsure_answer_climbs_one_rung_with_the_analysis_attached():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    state, acts = run(state, given(item, "lead", "unsure: needs a design call"))
    assert [(a["do"], a["to"]) for a in acts[0]] == [("escalate", "pm")]
    assert "needs a design call" in acts[0][0]["analysis"][-1]


def test_unsure_at_the_top_reaches_the_owner_with_a_safe_default_and_nothing_blocks():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    state, acts = run(state, given(item, "lead", "unsure: a"), given(item, "pm", "unsure: b"))
    ask = acts[1][0]
    assert ask["do"] == "notify-owner" and ask["default-if-silent"] == "wait"
    assert state["status"] == "running"


def test_only_the_entity_holding_the_item_may_answer_it():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    assert dos(run(state, given(item, "pm", "sure"))[1][0]) == ["error"]
    assert dos(run(state, given(item, "worker", "sure"))[1][0]) == ["error"]


def test_an_answer_must_be_sure_or_unsure_with_a_reason():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    for bad in ("maybe", "unsure", "unsure:  ", 3, None):
        assert dos(run(state, given(item, "lead", bad))[1][0]) == ["error"], bad


def test_an_answer_to_an_unknown_item_is_an_error():
    state, _ = started()
    assert dos(run(state, given("esc-99", "lead", "sure"))[1][0]) == ["error"]


def test_advice_from_an_unknown_entity_is_an_error():
    state, _ = started()
    assert dos(run(state, advice("ghost"))[1][0]) == ["error"]


def at_owner():
    state, _ = started()
    state, acts = run(state, advice("lead"))
    item = acts[0][0]["item"]
    state, acts = run(state, given(item, "pm", "unsure: your call"))
    return state, item


def test_an_owner_decision_is_rejected_when_no_verifier_is_given():
    state, item = at_owner()
    state, acts = run(state, owner(item, signature=sign(item, "yes")))
    assert dos(acts[0]) == ["error"]
    assert state["rejected"][-1]["event"]["type"] == "owner-decided"


def test_a_forged_owner_decision_is_rejected_and_logged():
    state, item = at_owner()
    state, acts = run(state, owner(item, signature="forged"), verify_owner=verifier)
    assert dos(acts[0]) == ["error"] and "signature" in acts[0][0]["reason"]
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "open"
    assert state["rejected"][-1]["event"]["signature"] == "forged"


def test_a_signature_for_one_decision_does_not_authorise_another():
    state, item = at_owner()
    state, acts = run(state, owner(item, "no", signature=sign(item, "yes")), verify_owner=verifier)
    assert dos(acts[0]) == ["error"]


def test_a_valid_owner_decision_closes_the_item():
    state, item = at_owner()
    state, acts = run(state, owner(item, "yes", sign(item, "yes")), verify_owner=verifier)
    assert dos(acts[0]) == ["owner-ruled"] and acts[0][0]["decision"] == "yes"
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "owner-ruled"


def test_an_owner_decision_for_an_item_not_at_the_owner_is_rejected():
    state, _ = started()
    state, acts = run(state, advice("worker"))
    item = acts[0][0]["item"]
    assert dos(run(state, owner(item, "yes", sign(item, "yes")), verify_owner=verifier)[1][0]) == ["error"]


def test_an_owner_item_cannot_be_decided_twice():
    state, item = at_owner()
    state, _ = run(state, owner(item, "yes", sign(item, "yes")), verify_owner=verifier)
    assert dos(run(state, owner(item, "yes", sign(item, "yes")), verify_owner=verifier)[1][0]) == ["error"]


def test_an_owner_decision_unblocks_a_blocked_run():
    state, _ = started()
    state, acts = run(state, {"type": "stage-failed", "stage": "align"})
    item = acts[0][0]["item"]
    assert state["status"] == "blocked"
    state, acts = run(state, owner(item, "retry", sign(item, "retry")), verify_owner=verifier)
    assert state["status"] == "running" and [a["stage"] for a in of(acts[0], "start-stage")] == ["align"]


def test_a_lead_may_spawn_a_worker():
    state, _ = started()
    state, acts = run(state, spawn("lead", "worker", "two reviews at once"))
    assert dos(acts[0]) == ["spawn"] and acts[0][0]["role"] == "worker" and acts[0][0]["by"] == "lead"
    assert state["spawned"][0]["why"] == "two reviews at once"


def test_a_worker_may_spawn_a_peer_because_may_spawn_lists_the_role():
    state, _ = started()
    assert dos(run(state, spawn("worker", "worker"))[1][0]) == ["spawn"]


def test_spawning_a_role_outside_may_spawn_is_rejected_and_nothing_starts():
    state, _ = started()
    state, acts = run(state, spawn("worker", "pm"))
    assert dos(acts[0]) == ["error"] and "pm" in acts[0][0]["reason"]
    assert not state.get("spawned") and state["rejected"][-1]["event"]["role"] == "pm"


def test_a_spawn_by_an_unknown_entity_or_of_an_unknown_role_is_rejected():
    state, _ = started()
    assert dos(run(state, spawn("ghost", "worker"))[1][0]) == ["error"]
    assert dos(run(state, spawn("lead", "ghost"))[1][0]) == ["error"]


def test_a_spawn_must_say_why():
    state, _ = started()
    assert dos(run(state, spawn("lead", "worker", why=""))[1][0]) == ["error"]


def test_a_spawn_past_the_agent_cap_is_rejected_and_the_owner_is_asked_to_raise_it():
    state, _ = started(policy={"max-agents": 2})
    state, acts = run(state, spawn("lead", "worker"), spawn("worker", "worker"), spawn("worker", "worker"))
    assert dos(acts[1]) == ["spawn"]
    assert dos(acts[2]) == ["notify-owner"] and "max-agents" in acts[2][0]["asks"]
    assert len(state["spawned"]) == 2


def test_a_spawn_chain_deeper_than_the_cap_is_rejected():
    state, _ = started(policy={"max-depth": 1})
    state, acts = run(state, spawn("lead", "worker"), spawn("worker", "worker", parent=1))
    assert dos(acts[0]) == ["spawn"] and dos(acts[1]) == ["notify-owner"]


def test_an_agent_cannot_answer_an_owner_item_by_claiming_to_be_the_owner():
    state, item = at_owner()
    for answer in ("sure: fine", "unsure: hmm"):
        after, acts = run(state, given(item, "owner", answer))
        assert dos(acts[0]) == ["error"]
        assert next(i for i in after["items"] if i["id"] == item)["status"] == "open"


def test_the_real_owner_can_still_decide_after_a_forged_answer_is_refused():
    state, item = at_owner()
    state, _ = run(state, given(item, "owner", "sure"))
    state, acts = run(state, owner(item, "yes", sign(item, "yes")), verify_owner=verifier)
    assert dos(acts[0]) == ["owner-ruled"]


@pytest.mark.parametrize("answer", ["no", 1, "yes", [True], {"ok": True}])
def test_a_verifier_must_return_exactly_true(answer):
    state, item = at_owner()
    state, acts = run(state, owner(item, "yes", "anything"), verify_owner=lambda e: answer)
    assert dos(acts[0]) == ["error"]


def test_a_verifier_that_raises_fails_closed():
    state, item = at_owner()
    state, acts = run(state, owner(item, "yes", "x"), verify_owner=lambda e: 1 / 0)
    assert dos(acts[0]) == ["error"]
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "open"


@pytest.mark.parametrize("cap", [True, False, -1, "3", 2.5, None])
def test_a_policy_cap_must_be_a_non_negative_integer(cap):
    with pytest.raises(ValueError, match="max-agents"):
        fresh(policy={"max-agents": cap})


def test_a_cap_of_zero_means_no_agent_may_be_spawned():
    state, _ = started(policy={"max-agents": 0})
    state, acts = run(state, spawn("lead", "worker"))
    assert dos(acts[0]) == ["notify-owner"] and not state.get("spawned")


@pytest.mark.parametrize("parent", [-1, 0, 99, True, "1", 1.0, [1]])
def test_a_spawn_parent_must_be_an_agent_the_runtime_issued(parent):
    state, _ = started(policy={"max-depth": 1})
    state, acts = run(state, spawn("lead", "worker"), spawn("worker", "worker", parent=parent))
    assert dos(acts[1]) == ["error"] and "parent" in acts[1][0]["reason"]
    assert len(state["spawned"]) == 1


def test_a_spawn_without_a_parent_is_a_root_agent_at_depth_one():
    state, _ = started()
    state, acts = run(state, spawn("lead", "worker"))
    assert acts[0][0]["depth"] == 1
