import json

import pytest
from procedure_testkit import HANDLERS, new_state, register, replay, step
from runtime_fixtures import LOCATORS, SWE, dos, done, fresh, of, run, snapshot, started


def test_a_procedure_that_fails_validation_cannot_start_a_run():
    with pytest.raises(ValueError, match="cycle"):
        new_state(SWE.replace("  align:\n    entity: pm\n", "  align:\n    needs: [integrate]\n    entity: pm\n", 1))


def test_a_new_run_has_not_started_and_every_stage_is_pending():
    state = fresh()
    assert state["status"] == "new"
    assert {s["status"] for s in state["stages"].values()} == {"pending"}


def test_run_started_starts_only_the_entry_stage():
    state, actions = started()
    assert state["status"] == "running"
    starts = [(a["do"], a["stage"], a["entity"]) for a in actions if a["do"] == "start-stage"]
    assert starts == [("start-stage", "align", "pm")]


def test_a_finished_stage_starts_the_next_with_only_the_kinds_it_consumes():
    state, _ = started()
    state, acts = run(state, done("align"))
    start = of(acts[0], "start-stage")
    assert [(a["stage"], a["inputs"]) for a in start] == [("spec", {"brief": "doc://brief"})]


def test_a_stage_never_sees_a_kind_it_does_not_consume():
    state, _ = started()
    state, acts = run(state, done("align"), done("spec"))
    assert of(acts[1], "start-stage")[0]["inputs"] == {"item": "issue://1"}


def test_the_whole_run_completes_in_order_and_ends_done():
    state, _ = started()
    seen = []
    for stage in ("align", "spec", "build", "review", "integrate"):
        state, acts = run(state, done(stage))
        seen += [a["stage"] for a in of(acts[0], "start-stage")]
    assert seen == ["spec", "build", "review", "integrate"]
    assert state["status"] == "done" and dos(acts[0]) == ["run-complete"]


def test_a_stage_done_without_a_locator_for_a_produced_kind_is_an_error_and_does_not_advance():
    state, _ = started()
    state, acts = run(state, done("align", {}))
    assert dos(acts[0]) == ["error"] and "brief" in acts[0][0]["reason"]
    assert state["stages"]["align"]["status"] == "running"


@pytest.mark.parametrize("bad", ["", "   ", 7, None, ["x"]])
def test_a_locator_must_be_non_empty_text(bad):
    state, _ = started()
    state, acts = run(state, done("align", {"brief": bad}))
    assert dos(acts[0]) == ["error"]
    assert state["stages"]["align"]["status"] == "running"


def test_a_stage_may_not_register_a_kind_it_does_not_produce():
    state, _ = started()
    state, acts = run(state, done("align", {"brief": "doc://b", "merged": "sha://forged"}))
    assert dos(acts[0]) == ["error"] and "merged" in acts[0][0]["reason"]


def test_a_stage_that_never_started_cannot_finish():
    state, _ = started()
    state, acts = run(state, done("build"))
    assert dos(acts[0]) == ["error"] and state["stages"]["build"]["status"] == "pending"


def test_an_unknown_stage_is_an_error():
    state, _ = started()
    assert dos(run(state, done("ghost", {}))[1][0]) == ["error"]


def test_stage_done_before_the_run_starts_is_an_error():
    assert dos(run(fresh(), done("align"))[1][0]) == ["error"]


def test_the_run_cannot_start_twice():
    state, _ = started()
    assert dos(run(state, {"type": "run-started"})[1][0]) == ["error"]


def test_events_after_the_run_is_done_are_errors():
    state, _ = started()
    for stage in ("align", "spec", "build", "review", "integrate"):
        state, _ = run(state, done(stage))
    assert dos(run(state, done("align"))[1][0]) == ["error"]


@pytest.mark.parametrize("bad", [None, "text", 7, [], {}, {"type": 3}, {"type": ""}])
def test_a_malformed_event_is_an_error_not_an_exception(bad):
    state, _ = started()
    after, acts = step(state, bad)
    assert dos(acts) == ["error"]
    assert after["stages"] == state["stages"]


def test_an_unknown_event_type_is_an_error_and_is_logged_as_rejected():
    state, _ = started()
    after, acts = step(state, {"type": "teleport"})
    assert dos(acts) == ["error"] and "teleport" in acts[0]["reason"]
    assert after["rejected"][-1]["event"]["type"] == "teleport"
    assert len(after["log"]) == len(state["log"])


def test_step_never_mutates_the_state_it_is_given():
    state, _ = started()
    before = snapshot(state)
    after, _ = step(state, done("align"))
    assert snapshot(state) == before and after is not state


def test_a_rejected_event_leaves_the_stages_unchanged():
    state, _ = started()
    after, _ = step(state, done("align", {}))
    assert after["stages"] == state["stages"]


def test_the_state_is_plain_data_that_survives_json():
    state, _ = started()
    state, _ = run(state, done("align"))
    assert json.loads(json.dumps(state)) == state


def test_replaying_a_recorded_log_gives_the_same_state_and_actions():
    events = [{"type": "run-started"}] + [done(s) for s in ("align", "spec", "build", "review", "integrate")]
    first = replay(SWE, events)
    second = replay(SWE, events)
    assert snapshot(first) == snapshot(second)
    state, acts = fresh(), []
    for ev in events:
        state, a = step(state, ev)
        acts.append(a)
    assert snapshot(first[0]) == snapshot(state)
    assert [a for batch in acts for a in batch] == first[1]


def test_a_new_event_type_needs_no_edit_to_the_core():
    @register("ping")
    def ping(state, event, ctx):
        state["pings"] = state.get("pings", 0) + 1
        return [{"do": "pong"}]

    try:
        state, _ = started()
        state, acts = run(state, {"type": "ping"}, {"type": "ping"})
        assert acts == [[{"do": "pong"}], [{"do": "pong"}]] and state["pings"] == 2
        assert state["log"][-1]["type"] == "ping"
    finally:
        HANDLERS.pop("ping", None)
    assert dos(step(started()[0], {"type": "ping"})[1]) == ["error"]


def test_a_handler_that_crashes_becomes_an_error_and_changes_nothing():
    @register("boom")
    def boom(state, event, ctx):
        state["half-done"] = True
        raise RuntimeError("bug")

    try:
        state, _ = started()
        after, acts = step(state, {"type": "boom"})
        assert dos(acts) == ["error"] and "half-done" not in after
    finally:
        HANDLERS.pop("boom", None)
