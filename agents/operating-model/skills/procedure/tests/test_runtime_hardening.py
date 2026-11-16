import json

import pytest
from procedure_testkit import step, validate_text
from runtime_fixtures import SWE, dos, done, failed, fresh, of, run, snapshot, started

NOTE = {"verdict": "note://defects"}
KEY = "owner-key"

SEC = SWE.replace(
    "  integrate:\n",
    "  audit:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [report]\n    metrics: [m]\n"
    "    when:\n      paths: [src/auth/**]\n  integrate:\n",
)


def at_review():
    state, _ = started()
    state, _ = run(state, done("align"), done("spec"), done("build"))
    return state


def exhaust():
    state = at_review()
    state, acts = run(
        state, failed("review", NOTE), done("build"), failed("review", NOTE), done("build"), failed("review", NOTE)
    )
    return state, acts[-1][0]["item"]


def given(item, by, answer):
    return {"type": "advice-given", "item": item, "by": by, "answer": answer}


def decided(item, decision="retry", sig="ok"):
    return {"type": "owner-decided", "item": item, "decision": decision, "signature": sig}


def ok(event):
    return True


# ---- a blocked run can always be resumed


def test_an_exhausted_loop_resumes_when_the_holder_answers_sure():
    state, item = exhaust()
    state, acts = run(state, given(item, "lead", "sure: one more try"))
    assert state["status"] == "running"
    assert [(a["stage"], a["round"]) for a in of(acts[0], "start-stage")] == [("build", 1)]


def test_an_exhausted_loop_resumes_after_a_verified_owner_decision():
    state, item = exhaust()
    state, _ = run(state, given(item, "lead", "unsure: a"), given(item, "pm", "unsure: b"))
    state, acts = run(state, decided(item), verify_owner=ok)
    assert state["status"] == "running" and of(acts[0], "start-stage")


def test_a_resumed_loop_gets_a_fresh_bound():
    state, item = exhaust()
    state, _ = run(state, given(item, "lead", "sure: go"))
    state, acts = run(state, done("build"), failed("review", NOTE))
    assert of(acts[1], "start-stage") and state["status"] == "running"


def test_a_failed_stage_blocked_on_an_entity_resumes_when_that_entity_answers_sure():
    state, _ = started()
    state, acts = run(state, done("align"))
    state, acts = run(state, failed("spec"))
    item = acts[0][0]["item"]
    state, acts = run(state, given(item, "pm", "sure: retry it"))
    assert state["status"] == "running" and [a["stage"] for a in of(acts[0], "start-stage")] == ["spec"]


def test_an_unsure_answer_does_not_resume_a_blocked_run():
    state, item = exhaust()
    state, _ = run(state, given(item, "lead", "unsure: no idea"))
    assert state["status"] == "blocked"


def test_an_owner_abort_halts_the_run_for_good():
    state, item = exhaust()
    state, _ = run(state, given(item, "lead", "unsure: a"), given(item, "pm", "unsure: b"))
    state, acts = run(state, decided(item, "abort"), verify_owner=ok)
    assert state["status"] == "halted" and dos(acts[0]) == ["owner-ruled", "run-halted"]
    assert dos(run(state, done("build"))[1][0]) == ["error"]


# ---- a loop reset leaves no stale stage behind


def test_a_side_branch_that_saw_the_old_round_is_redone_when_the_loop_runs_again():
    state = fresh(SEC)
    state, _ = run(state, {"type": "run-started", "changed": ["src/auth/x.py"]})
    state, _ = run(state, done("align"), done("spec"), done("build"), done("audit", {"report": "r://1"}))
    state, acts = run(state, failed("review", NOTE))
    assert state["stages"]["audit"]["status"] == "pending"
    state, acts = run(state, done("build", {"change": "pr://8"}))
    assert {a["stage"] for a in of(acts[0], "start-stage")} == {"review", "audit"}


def test_a_stage_still_running_on_stale_input_is_cancelled_and_its_late_result_refused():
    state = fresh(SEC)
    state, _ = run(state, {"type": "run-started", "changed": ["src/auth/x.py"]})
    state, _ = run(state, done("align"), done("spec"), done("build"))
    state, acts = run(state, failed("review", NOTE))
    assert {"do": "stage-cancelled", "stage": "audit", "why": "its input is being redone"} in acts[0]
    assert dos(run(state, done("audit", {"report": "r://late"}))[1][0]) == ["error"]


def test_on_fail_also_redoes_stages_downstream_of_the_retry_target():
    text = SWE.replace(
        "loops:\n  fix:\n    stages: [build, review]\n    exit:\n      kind: verdict\n    bound: 3\n    on-exhausted: lead\n    carries: verdict\n",
        "",
    ).replace(
        "    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [verdict]",
        "    entity: lead\n    on-fail:\n      to: build\n      bound: 2 rounds\n    needs: [build]\n    consumes: [change]\n    produces: [verdict]",
    )
    text = text.replace(
        "  integrate:\n",
        "  lint:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [lint-report]\n    metrics: [m]\n  integrate:\n",
    )
    state, _ = started(text)
    state, _ = run(state, done("align"), done("spec"), done("build"), done("lint", {"lint-report": "l://1"}))
    state, acts = run(state, failed("review", {}))
    assert state["stages"]["lint"]["status"] == "pending"
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["build"]


# ---- spawn and advice need a live run


@pytest.mark.parametrize("event", [
    {"type": "spawn-requested", "by": "lead", "role": "worker", "why": "w"},
    {"type": "advice-requested", "from": "worker", "question": "q"},
])
def test_spawn_and_advice_are_refused_on_a_run_that_has_not_started(event):
    assert dos(step(fresh(), event)[1]) == ["error"]


def test_spawn_and_advice_are_refused_after_the_run_is_done():
    state, _ = started()
    for stage in ("align", "spec", "build", "review", "integrate"):
        state, _ = run(state, done(stage))
    assert dos(step(state, {"type": "spawn-requested", "by": "lead", "role": "worker", "why": "w"})[1]) == ["error"]


def test_spawn_and_advice_still_work_while_the_run_is_blocked():
    state, _ = exhaust()
    assert dos(step(state, {"type": "spawn-requested", "by": "lead", "role": "worker", "why": "w"})[1]) == ["spawn"]


def test_the_depth_cap_cannot_be_dodged_by_leaving_out_the_parent():
    state, _ = started(policy={"max-depth": 1})
    state, acts = run(
        state,
        {"type": "spawn-requested", "by": "lead", "role": "worker", "why": "w"},
        {"type": "spawn-requested", "by": "worker", "role": "worker", "why": "w"},
    )
    assert dos(acts[0]) == ["spawn"] and dos(acts[1]) == ["notify-owner"]


# ---- step never raises


def deep(n):
    x = []
    for _ in range(n):
        x = [x]
    return x


@pytest.mark.parametrize("event", [
    pytest.param(10**5000, id="huge-int"),
    pytest.param({"type": "advice-requested", "from": "worker", "question": "q", "x": deep(3000)}, id="deep-accepted-type"),
    pytest.param({"type": "zzz", "x": deep(3000)}, id="deep-unknown-type"),
    pytest.param({"type": "advice-requested", "from": "worker", "question": "q", "x": ["a"] * 200000}, id="wide"),
    pytest.param({"type": "advice-requested", "from": "worker", "question": "q", 5: "non-string key"}, id="int-key"),
])
def test_a_hostile_event_is_an_error_and_never_raises(event):
    state, _ = started()
    after, acts = step(state, event)
    assert dos(acts) == ["error"]
    assert len(json.dumps(after["rejected"])) < 2000
    assert after["stages"] == state["stages"]


def test_a_run_still_works_after_a_hostile_event_was_refused():
    state, _ = started()
    state, _ = step(state, {"type": "zzz", "x": deep(3000)})
    state, acts = run(state, done("align"))
    assert of(acts[0], "start-stage")


# ---- carried values


def test_a_failure_may_only_carry_text_locators():
    state = at_review()
    for bad in ({"a": 1}, ["x"], 7, "", None):
        assert dos(run(state, failed("review", {"verdict": bad}))[1][0]) == ["error"], bad


def test_a_carried_value_does_not_outlive_the_round_that_set_it():
    state = at_review()
    state, _ = run(state, failed("review", NOTE), done("build"))
    state, acts = run(state, failed("review", {}))
    assert "verdict" not in of(acts[0], "start-stage")[0]["inputs"]


def test_a_carried_value_is_cleared_when_the_loop_finishes():
    state = at_review()
    state, _ = run(state, failed("review", NOTE), done("build"), done("review"))
    assert not state.get("carried")


# ---- paths, aliasing, identity


@pytest.mark.parametrize("path", ["./src/auth/x.py", "src//auth/x.py", "src/auth/../auth/x.py"])
def test_changed_paths_are_normalised_before_matching(path):
    state = fresh(SEC)
    state, _ = run(state, {"type": "run-started", "changed": [path]})
    state, _ = run(state, done("align"), done("spec"), done("build"))
    assert state["stages"]["audit"]["status"] == "running"


@pytest.mark.parametrize("path", ["../outside/x.py", "/etc/passwd"])
def test_a_changed_path_that_leaves_the_project_is_refused(path):
    assert dos(run(fresh(SEC), {"type": "run-started", "changed": [path]})[1][0]) == ["error"]


def test_the_state_does_not_alias_objects_the_caller_still_holds():
    state, item = exhaust()
    state, _ = run(state, given(item, "lead", "unsure: a"), given(item, "pm", "unsure: b"))
    event = decided(item, "retry")
    event["note"] = {"k": 1}
    after, acts = step(state, event, verify_owner=ok)
    event["note"]["k"] = 99
    acts[0]["decision"] = "tampered"
    assert [i for i in after["items"] if i["id"] == item][0]["decision"] == "retry"
    assert json.dumps(after["log"]).count("99") == 0


def test_the_owner_verifier_sees_the_run_id_so_a_decision_cannot_be_replayed_in_another_run():
    seen = []

    def bound(event):
        seen.append(event.get("run_id"))
        return event.get("run_id") == "run-A"

    a, item = exhaust()
    a["run_id"] = "run-A"
    state, _ = run(a, given(item, "lead", "unsure: a"), given(item, "pm", "unsure: b"))
    assert dos(run(state, decided(item), verify_owner=bound)[1][0]) != ["error"]
    state["run_id"] = "run-B"
    state["items"][-1]["status"] = "open"
    assert dos(run(state, decided(item), verify_owner=bound)[1][0]) == ["error"]
    assert seen == ["run-A", "run-B"]


# ---- the format side of the same problems


FLOOR_WHEN = SWE.replace(
    "  integrate:\n    entity: pm\n", "  integrate:\n    floor: true\n    when:\n      policy: p\n    entity: pm\n"
)


def test_a_floor_stage_cannot_carry_its_own_when():
    assert any("floor" in e for e in validate_text(FLOOR_WHEN))


def test_a_stage_that_names_an_entity_when_none_are_defined_can_still_fail_and_escalate():
    text = SWE.replace(SWE[SWE.index("entities:"):SWE.index("kpis:")], "").replace("    on-exhausted: lead", "    on-exhausted: owner").replace(
        "    entity: pm\n", "    entity: ghost\n"
    )
    state, _ = started(text)
    state, acts = run(state, failed("align"))
    assert dos(acts[0]) in (["notify-owner"], ["escalate"])
