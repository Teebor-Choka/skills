import json

import pytest
from procedure_testkit import HANDLERS, new_state, register, replay, step
from runtime_fixtures import SWE, dos, fresh, of, snapshot, started
from signed_fixtures import (VERIFIERS, go, owner_sign, sdone, seal, sfailed, sfresh, srun, verify_executor,
                             verify_sender)


def refused(acts, word=None):
    return dos(acts) == ["error"] and (word is None or word in acts[0]["reason"])


# ---- the mode


def test_a_run_is_in_claims_mode_unless_it_asks_for_signed():
    assert fresh()["trust"] == "claims" and sfresh()["trust"] == "signed"


def test_an_unknown_trust_mode_is_refused():
    with pytest.raises(ValueError, match="trust"):
        new_state(SWE, trust="open")


def test_claims_mode_still_accepts_unsigned_events():
    state, acts = started()
    assert of(acts, "start-stage")


# ---- executor facts


def test_in_signed_mode_run_started_must_come_from_the_executor():
    state, acts = srun(sfresh(), {"type": "run-started"})
    assert refused(acts[0], "executor")
    state, acts = srun(sfresh(), seal({"type": "run-started"}, "pm"))
    assert refused(acts[0], "executor")


def test_a_correctly_signed_executor_event_starts_the_run():
    state, acts = go()
    assert state["status"] == "running" and of(acts, "start-stage")


def test_no_executor_verifier_means_no_executor_event_is_accepted():
    state, acts = srun(sfresh(), seal({"type": "run-started"}, "executor"), verify_executor=None)
    assert refused(acts[0])


def test_an_executor_verifier_that_raises_fails_closed():
    state, acts = srun(sfresh(), seal({"type": "run-started"}, "executor"), verify_executor=lambda e: 1 / 0)
    assert refused(acts[0])


@pytest.mark.parametrize("answer", ["yes", 1, [True], {"ok": 1}])
def test_an_executor_verifier_must_return_exactly_true(answer):
    state, acts = srun(sfresh(), seal({"type": "run-started"}, "executor"), verify_executor=lambda e: answer)
    assert refused(acts[0])


def test_an_agent_cannot_send_an_executor_event_even_with_a_valid_agent_signature():
    state, acts = srun(sfresh(), seal({"type": "run-started"}, "lead"))
    assert refused(acts[0]) and state["status"] == "new"


# ---- the sender must be who the event says


def test_advice_is_accepted_when_the_verified_sender_is_the_asker():
    state, _ = go()
    state, acts = srun(state, seal({"type": "advice-requested", "from": "worker", "question": "q"}, "worker"))
    assert dos(acts[0]) == ["escalate"]


def test_an_agent_cannot_ask_for_advice_as_another_entity():
    state, _ = go()
    state, acts = srun(state, seal({"type": "advice-requested", "from": "worker", "question": "q"}, "lead"))
    assert refused(acts[0], "sender")


def test_an_agent_cannot_answer_advice_as_the_project_manager():
    state, _ = go()
    state, acts = srun(state, seal({"type": "advice-requested", "from": "lead", "question": "q"}, "lead"))
    item = acts[0][0]["item"]
    state, acts = srun(state, seal({"type": "advice-given", "item": item, "by": "pm", "answer": "sure"}, "worker"))
    assert refused(acts[0], "sender")
    state, acts = srun(state, seal({"type": "advice-given", "item": item, "by": "pm", "answer": "sure"}, "pm"))
    assert dos(acts[0]) == ["advice-resolved"]


def test_an_agent_cannot_spawn_as_another_entity():
    state, _ = go()
    forged = seal({"type": "spawn-requested", "by": "pm", "role": "lead", "why": "x"}, "worker")
    assert refused(srun(state, forged)[1][0], "sender")
    ok = seal({"type": "spawn-requested", "by": "lead", "role": "worker", "why": "x"}, "lead")
    assert dos(srun(state, ok)[1][0]) == ["spawn"]


def test_an_agent_cannot_propose_a_change_as_another_entity():
    from metrics_fixtures import MET, delta
    state, _ = go(MET)
    forged = seal({"type": "amendment-proposed", "by": "pm", "delta": delta()}, "worker")
    assert refused(srun(state, forged)[1][0], "sender")


def test_a_stage_result_must_come_from_the_entity_that_runs_the_stage():
    state, _ = go()
    state, acts = srun(state, sdone("align", by="worker"))
    assert refused(acts[0], "sender") and state["stages"]["align"]["status"] == "running"
    state, acts = srun(state, sdone("align"))
    assert of(acts[0], "start-stage")


def test_a_stage_failure_must_come_from_the_entity_that_runs_the_stage():
    state, _ = go()
    state, acts = srun(state, sfailed("align", by="lead"))
    assert refused(acts[0], "sender") and state["status"] == "running"
    state, acts = srun(state, sfailed("align"))
    assert state["status"] == "blocked"


# ---- the signature itself


def test_a_tampered_event_is_refused():
    state, _ = go()
    event = sdone("align")
    event["locators"] = {"brief": "doc://swapped"}
    assert refused(srun(state, event)[1][0], "sender")


def test_an_event_signed_with_another_entitys_key_is_refused():
    state, _ = go()
    event = sdone("align")
    event["sender"] = "worker"  # claims to be the worker, signature is the pm's
    assert refused(srun(state, event)[1][0], "sender")


def test_an_event_signed_for_another_run_is_refused():
    state, _ = go(run_id="run-B")
    event = seal({"type": "advice-requested", "from": "worker", "question": "q"}, "worker", run_id="run-A")
    assert refused(srun(state, event)[1][0], "sender")


def test_an_event_with_no_signature_is_refused():
    state, _ = go()
    event = sdone("align")
    del event["signature"]
    assert refused(srun(state, event)[1][0], "sender")


def test_no_sender_verifier_means_no_agent_event_is_accepted():
    state, _ = go()
    assert refused(srun(state, sdone("align"), verify_sender=None)[1][0], "sender")


def test_a_sender_verifier_that_raises_fails_closed():
    state, _ = go()
    assert refused(srun(state, sdone("align"), verify_sender=lambda e: 1 / 0)[1][0], "sender")


@pytest.mark.parametrize("answer", [True, 1, "owner", "ghost", None, ["pm"], ""])
def test_a_sender_verifier_must_return_a_defined_entity(answer):
    state, _ = go()
    assert refused(srun(state, sdone("align"), verify_sender=lambda e: answer)[1][0], "sender")


def test_the_verifier_cannot_change_an_event_the_reducer_goes_on_to_use():
    state, _ = go()

    def meddling(event):
        event["stage"] = "spec"
        event["locators"] = {"item": "x"}
        return "pm"

    state, acts = srun(state, sdone("align"), verify_sender=meddling)
    assert state["stages"]["align"]["status"] == "done" and state["stages"]["spec"]["status"] == "running"


# ---- the owner path is unchanged and agents cannot use it


def test_an_agent_cannot_send_an_owner_decision_through_the_agent_path():
    state, _ = go()
    state, acts = srun(state, sfailed("align"))
    item = acts[0][0]["item"]
    forged = seal({"type": "owner-decided", "item": item, "decision": "retry"}, "pm")
    assert refused(srun(state, forged)[1][0])
    ok = {"type": "owner-decided", "item": item, "decision": "retry", "signature": owner_sign(item, "retry")}
    assert dos(srun(state, ok)[1][0])[0] == "owner-ruled"


# ---- the registry knows each event's source


def test_a_registered_event_defaults_to_an_agent_source_that_needs_a_verified_sender():
    @register("ping")
    def ping(state, event, ctx):
        return [{"do": "pong", "who": ctx.sender}]

    try:
        state, _ = go()
        assert refused(srun(state, {"type": "ping"})[1][0], "sender")
        state, acts = srun(state, seal({"type": "ping"}, "lead"))
        assert acts[0] == [{"do": "pong", "who": "lead"}]
    finally:
        HANDLERS.pop("ping", None)


def test_a_registered_event_can_declare_an_executor_source():
    @register("tick", source="executor")
    def tick(state, event, ctx):
        return [{"do": "ticked"}]

    try:
        state, _ = go()
        assert refused(srun(state, seal({"type": "tick"}, "lead"))[1][0], "executor")
        assert dos(srun(state, seal({"type": "tick"}, "executor"))[1][0]) == ["ticked"]
    finally:
        HANDLERS.pop("tick", None)


def test_registering_an_unknown_source_is_an_error():
    with pytest.raises(ValueError, match="source"):
        register("x", source="stranger")(lambda s, e, c: [])


# ---- the record


def test_a_refused_signed_event_is_logged_and_counts_as_a_refusal():
    state, _ = go()
    state, _ = srun(state, sdone("align", by="worker"))
    assert state["log"][-1]["sender"] == "worker" and state["metrics"]["1"]["refusals"] == 1


def test_a_signed_run_replays_exactly_with_the_same_verifiers():
    events = [seal({"type": "run-started"}, "executor"), sdone("align"), sdone("spec"), sdone("align", by="worker")]
    first = replay(SWE, events, trust="signed", **VERIFIERS)
    second = replay(SWE, events, trust="signed", **VERIFIERS)
    assert snapshot(first) == snapshot(second) and first[0]["stages"]["spec"]["status"] == "done"


def test_the_signed_state_survives_json():
    state, _ = go()
    assert json.loads(json.dumps(state))["trust"] == "signed"


def test_a_handler_added_without_declaring_a_source_is_refused_in_a_signed_run():
    HANDLERS["sneaky"] = lambda state, event, ctx: [{"do": "ran"}]
    try:
        state, _ = go()
        for sender in ("lead", "executor"):
            assert refused(srun(state, seal({"type": "sneaky"}, sender))[1][0], "source")
        from runtime_fixtures import started
        assert dos(step(started()[0], {"type": "sneaky"})[1]) == ["ran"]  # claims mode has no sources
    finally:
        HANDLERS.pop("sneaky", None)
