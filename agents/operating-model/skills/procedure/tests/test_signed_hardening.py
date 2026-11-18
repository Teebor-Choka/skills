import json

import pytest
from procedure_testkit import HANDLERS, register, replay, step
from runtime_fixtures import SWE, dos, of, snapshot
from metrics_fixtures import MET, delta
from signed_fixtures import (VERIFIERS, decide, go, owner_sign, sdone, seal, sfailed, sfresh, srun, verify_sender)
from validate_procedure import apply_delta, parse_procedure


def refused(acts, word=None):
    return dos(acts) == ["error"] and (word is None or word in acts[0]["reason"])


def counters(state, version=None):
    return state["metrics"][str(version or state["version"])]


def advice(by="worker", **kw):
    return seal({"type": "advice-requested", "from": by, "question": "q", **kw}, by)


def amend(text, by="lead"):
    return seal({"type": "amendment-proposed", "by": by, "delta": text}, by)


# ---- 1. an event that was not authenticated moves nothing


@pytest.mark.parametrize("junk", [
    {"type": "stage-done"},
    {"type": "teleport"},
    {"type": "stage-done", "stage": "align", "sender": "pm", "signature": "forged", "locators": {"brief": "x"}},
    "not an event",
    10 ** 40,
])
def test_an_unauthenticated_event_changes_no_metric_and_no_log(junk):
    state, _ = go()
    before = (json.dumps(counters(state), sort_keys=True), len(state["log"]))
    state, acts = srun(state, junk)
    assert dos(acts[0]) == ["error"]
    assert (json.dumps(counters(state), sort_keys=True), len(state["log"])) == before


def test_a_verified_entity_that_breaks_a_rule_is_still_counted():
    state, _ = go()
    state, acts = srun(state, sdone("align", by="worker"))
    assert refused(acts[0], "sender")
    assert counters(state)["refusals"] == 1  # `worker` verified, so it is counted when it breaks a rule
    state, acts = srun(state, seal({"type": "spawn-requested", "by": "worker", "role": "pm", "why": "x"}, "worker"))
    assert dos(acts[0]) == ["error"] and counters(state)["refusals"] == 2


def test_unauthenticated_junk_cannot_roll_back_an_approved_change():
    policy = {"safety-metrics": ["refusals"]}
    state, _ = go(MET, policy=policy)
    state, a = srun(state, amend(delta(window="2 stages")))
    item = a[0][0]["item"]
    state, _ = srun(state, decide(state, item, "approve"))
    state, _ = srun(state, sdone("align"))
    assert state["version"] == 2
    state, _ = srun(state, {"type": "stage-done"}, {"type": "teleport"}, seal({"type": "x"}, "pm"))
    state, _ = srun(state, sdone("spec"), sdone("build"))
    assert state["version"] == 2 and state["snapshots"][1]["outcome"] == "confirmed"


def test_a_flood_of_unauthenticated_events_does_not_grow_the_state():
    state, _ = go()
    size = len(json.dumps(state))
    for _ in range(300):
        state, _ = srun(state, {"type": "nope", "x": "y" * 50})
    assert len(json.dumps(state)) <= size + 100


def test_the_rejected_list_is_bounded():
    state, _ = go()
    for i in range(400):
        state, _ = srun(state, seal({"type": "spawn-requested", "by": "worker", "role": "pm", "why": f"w{i}"}, "worker"))
    assert len(state["rejected"]) <= 200 and counters(state)["refusals"] == 400


# ---- 2. a signed event is single-use and bound to its round


def test_the_same_signed_event_cannot_be_applied_twice():
    state, _ = go()
    spawn = seal({"type": "spawn-requested", "by": "lead", "role": "worker", "why": "x"}, "lead")
    state, acts = srun(state, spawn, spawn, spawn)
    assert dos(acts[0]) == ["spawn"] and refused(acts[1], "replay") and refused(acts[2], "replay")
    assert len(state["spawned"]) == 1


def test_a_replayed_event_is_not_counted_so_it_cannot_move_a_metric():
    state, _ = go()
    ev = advice()
    state, _ = srun(state, ev)
    before = counters(state)["escalations"], counters(state)["refusals"]
    state, _ = srun(state, ev, ev, ev)
    assert (counters(state)["escalations"], counters(state)["refusals"]) == before


def test_a_refused_signed_event_may_be_sent_again_after_the_cause_is_fixed():
    state, _ = go()
    ev = seal({"type": "spawn-requested", "by": "lead", "role": "worker", "why": "x", "parent": 9}, "lead")
    state, acts = srun(state, ev)
    assert dos(acts[0]) == ["error"]
    state, acts = srun(state, seal({"type": "spawn-requested", "by": "lead", "role": "worker", "why": "x"}, "lead"))
    assert dos(acts[0]) == ["spawn"]


def test_a_round_one_result_is_refused_in_round_two():
    state, _ = go()
    state, _ = srun(state, sdone("align"), sdone("spec"))
    d1 = sdone("build")
    state, _ = srun(state, d1, sfailed("review", locators={"verdict": "note://d"}, by="lead"))
    assert state["stages"]["build"]["status"] == "running" and state["stages"]["build"]["round"] == 2
    state, acts = srun(state, sdone("build", round=1))
    assert refused(acts[0], "replay")  # the very same bytes are caught first
    stale = sdone("build", locators={"change": "pr://other"}, round=1)  # a different round-one result
    state, acts = srun(state, stale)
    assert refused(acts[0], "round") and state["stages"]["build"]["status"] == "running"
    state, acts = srun(state, sdone("build", round=2))
    assert of(acts[0], "start-stage")


def test_a_failure_for_the_wrong_round_is_refused():
    state, _ = go()
    state, acts = srun(state, sfailed("align", round=7))
    assert refused(acts[0], "round") and state["status"] == "running"


def test_a_stage_result_with_no_round_is_refused_in_a_signed_run():
    state, _ = go()
    ev = seal({"type": "stage-done", "stage": "align", "locators": {"brief": "doc://b"}}, "pm")
    assert refused(srun(state, ev)[1][0], "round")


@pytest.mark.parametrize("bad", [True, "1", 1.0, None, [1]])
def test_a_round_must_be_an_integer(bad):
    state, _ = go()
    ev = seal({"type": "stage-done", "stage": "align", "round": bad, "locators": {"brief": "doc://b"}}, "pm")
    assert refused(srun(state, ev)[1][0], "round")


def test_an_owner_retry_is_not_cancelled_by_replaying_the_failure():
    state, _ = go()
    fail = sfailed("align")
    state, acts = srun(state, fail)
    item = acts[0][0]["item"]
    state, _ = srun(state, decide(state, item, "retry"))
    assert state["stages"]["align"]["status"] == "running"
    state, acts = srun(state, fail)
    assert refused(acts[0], "replay") and state["status"] == "running"


def test_the_seen_signatures_survive_json_and_replay():
    state, _ = go()
    ev = advice()
    state, _ = srun(state, ev)
    again = json.loads(json.dumps(state))
    assert refused(srun(again, ev)[1][0], "replay")
    first = replay(SWE, [seal({"type": "run-started"}, "executor"), ev, ev], trust="signed", **VERIFIERS)
    assert snapshot(first) == snapshot(replay(SWE, [seal({"type": "run-started"}, "executor"), ev, ev], trust="signed", **VERIFIERS))


# ---- 3. an owner decision is bound to the run and to what it decides


def at_owner(run_id="run"):
    state, _ = go(run_id=run_id)
    state, acts = srun(state, sfailed("align", run_id=run_id))
    return state, acts[0][0]["item"]


def test_an_owner_decision_signed_for_another_run_is_refused():
    a, item_a = at_owner("run-A")
    b, item_b = at_owner("run-B")
    assert item_a == item_b == "esc-1"
    captured = decide(a, item_a, "retry")
    state, acts = srun(b, captured)
    assert refused(acts[0], "signature") and state["stages"]["align"]["status"] == "failed"


def test_an_owner_decision_signed_for_other_content_is_refused():
    state, item = at_owner()
    signed = decide(state, item, "retry")
    state["items"][0]["asks"] = "a different question entirely"
    assert refused(srun(state, signed)[1][0], "signature")


def test_the_digest_tells_two_items_with_the_same_text_apart():
    state, _ = go()
    state, _ = srun(state, advice(), advice("lead", question="q"))
    from runtime import item_digest
    state, _ = srun(state, seal({"type": "advice-requested", "from": "worker", "question": "q", "n": 2}, "worker"))
    assert item_digest(state, "esc-1") != item_digest(state, "esc-3")


def test_an_item_digest_for_an_unknown_item_is_an_error():
    from runtime import item_digest
    state, _ = go()
    with pytest.raises(KeyError):
        item_digest(state, "esc-99")


# ---- 4. an amendment that moves authority is flagged and shown


@pytest.mark.parametrize("body", [
    "entities:\n  lead:\n    role: project-manager\n",
    "entities:\n  lead:\n    may-spawn: [worker, worker]\n",
    "entities:\n  worker:\n    disabled: true\n",
    "stages:\n  build:\n    entity: lead\n",
])
def test_a_change_to_who_holds_authority_is_a_protected_change(body):
    from metrics_fixtures import MET
    base, _ = parse_procedure(MET, "<b>")
    merged, errs, protected = apply_delta(base, delta(body), ratified=True)
    assert protected is True


def test_adding_an_entity_or_changing_a_stage_tier_is_not_protected():
    from metrics_fixtures import MET
    base, _ = parse_procedure(MET, "<b>")
    merged, errs, protected = apply_delta(base, delta("entities:\n  helper:\n    escalates-to: worker\n"), ratified=True)
    assert errs == [] and protected is False


def test_the_owner_is_shown_the_delta_and_that_it_moves_authority():
    state, _ = go(MET)
    body = "entities:\n  lead:\n    role: project-manager\n"
    state, acts = srun(state, amend(delta(body)))
    ask = acts[0][0]
    assert ask["protected"] is True and "project-manager" in ask["delta"]


# ---- 5. removing an entity does not strand its open items


def test_an_open_item_held_by_a_removed_entity_moves_up_the_ladder():
    state, _ = go(MET)
    state, a = srun(state, advice("worker"))
    item = a[0][0]["item"]
    assert state["items"][0]["at"] == "lead"
    gone = (
        "entities:\n  lead:\n    disabled: true\n  pm:\n    may-spawn: [worker]\n  worker:\n    escalates-to: pm\n"
        "loops:\n  fix:\n    on-exhausted: pm\n"
        "stages:\n  spec:\n    entity: pm\n  review:\n    entity: pm\n"
    )
    state, a = srun(state, amend(delta(gone, window="2 stages")))
    state, _ = srun(state, decide(state, a[0][0]["item"], "approve"))
    state, acts = srun(state, sdone("align"))
    held = next(i for i in state["items"] if i["id"] == item)
    assert held["at"] == "pm" and any(x["do"] == "item-reassigned" for x in acts[0])


# ---- 6. a verifier cannot leak or meddle


def test_a_str_subclass_from_a_verifier_is_not_a_sender():
    class Liar(str):
        def __eq__(self, other):
            return True

        __hash__ = str.__hash__

    state, _ = go()
    assert refused(srun(state, sdone("align"), verify_sender=lambda e: Liar("pm"))[1][0], "sender")


def test_a_verify_owner_exception_does_not_leak_into_the_record():
    state, item = at_owner()
    state, acts = srun(state, decide(state, item, "retry"), verify_owner=lambda e: (_ for _ in ()).throw(ValueError("secret-key-material")))
    assert refused(acts[0]) and "secret-key-material" not in json.dumps(state) + json.dumps(acts)


def test_verify_owner_cannot_change_the_decision_the_reducer_stores():
    state, item = at_owner()

    def meddling(event):
        event["decision"]["action"] = "abort"
        return True

    ev = {"type": "owner-decided", "item": item, "decision": {"action": "retry"}, "signature": "x"}
    state, acts = srun(state, ev, verify_owner=meddling)
    assert state["items"][0]["decision"] == {"action": "retry"} and state["status"] == "running"


# ---- replaying a refused event must not move a metric either

def test_a_refused_signed_event_replayed_is_not_counted_again():
    state, _ = go()
    ev = seal({"type": "spawn-requested", "by": "lead", "role": "worker", "why": "x", "parent": 9}, "lead")
    state, acts = srun(state, ev)
    assert dos(acts[0]) == ["error"]
    after_first = (counters(state)["refusals"], len(state["log"]))
    state, acts = srun(state, ev, ev, ev)
    assert all(refused(a, "replay") for a in acts)
    assert (counters(state)["refusals"], len(state["log"])) == after_first


def test_an_applied_owner_decision_replayed_is_not_counted():
    from signed_fixtures import decide
    state, _ = go()
    state, acts = srun(state, sfailed("align"))
    ev = decide(state, acts[0][0]["item"], "retry")
    state, acts = srun(state, ev)
    assert dos(acts[0])[0] == "owner-ruled"
    before = (counters(state)["refusals"], len(state["log"]))
    state, acts = srun(state, ev)
    assert refused(acts[0], "replay")
    assert (counters(state)["refusals"], len(state["log"])) == before
