import pytest
from runtime_fixtures import LOCATORS, SWE, dos, done, failed, fresh, of, run, started

THROUGH_SPEC = [done("align"), done("spec")]
NOTE = {"verdict": "note://defects"}


def at_review(text=SWE, **kw):
    state, _ = started(text, **kw)
    state, _ = run(state, *THROUGH_SPEC, done("build"))
    return state


def test_a_failed_review_sends_the_loop_back_to_build_with_the_carried_kind():
    state = at_review()
    state, acts = run(state, failed("review", NOTE))
    start = of(acts[0], "start-stage")
    assert [(a["stage"], a["round"]) for a in start] == [("build", 2)]
    assert start[0]["inputs"] == {"item": "issue://1", "verdict": "note://defects"}
    assert state["stages"]["review"]["status"] == "pending"


def test_a_loop_that_converges_moves_on_after_the_clean_review():
    state = at_review()
    state, _ = run(state, failed("review", NOTE), done("build"))
    state, acts = run(state, done("review"))
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["integrate"]


def test_the_round_number_counts_each_pass_through_the_loop():
    state = at_review()
    state, acts = run(state, failed("review", NOTE), done("build"), failed("review", NOTE))
    assert of(acts[2], "start-stage")[0]["round"] == 3


def test_when_the_bound_is_spent_the_loop_escalates_and_the_run_blocks():
    state = at_review()
    state, acts = run(state, failed("review", NOTE), done("build"), failed("review", NOTE), done("build"), failed("review", NOTE))
    last = acts[-1]
    assert dos(last) == ["escalate"] and last[0]["to"] == "lead" and "fix" in last[0]["asks"]
    assert state["status"] == "blocked" and not of(last, "start-stage")


def test_a_blocked_run_refuses_stage_events():
    state = at_review()
    state, _ = run(state, failed("review", NOTE), done("build"), failed("review", NOTE), done("build"), failed("review", NOTE))
    assert dos(run(state, done("review"))[1][0]) == ["error"]


def test_a_failed_stage_must_be_running():
    state, _ = started()
    assert dos(run(state, failed("build"))[1][0]) == ["error"]


def test_a_failure_may_not_register_a_kind_the_stage_does_not_produce():
    state = at_review()
    assert dos(run(state, failed("review", {"merged": "sha://x"}))[1][0]) == ["error"]


def test_a_failure_outside_any_loop_climbs_the_entity_ladder():
    state, _ = started()
    state, acts = run(state, failed("align"))
    assert dos(acts[0]) == ["notify-owner"] and acts[0][0]["default-if-silent"] == "wait"
    assert state["status"] == "blocked"


def test_a_failure_escalates_to_the_entity_above_the_stage_owner():
    state, _ = started()
    state, _ = run(state, done("align"))
    state, acts = run(state, failed("spec"))
    assert acts[0][0]["to"] == "pm" and dos(acts[0]) == ["escalate"]


RETRY = SWE.replace(
    "loops:\n  fix:\n    stages: [build, review]\n    exit:\n      kind: verdict\n    bound: 3\n    on-exhausted: lead\n    carries: verdict\n",
    "",
).replace("    entity: worker\n    needs: [spec]", "    entity: worker\n    on-fail:\n      to: build\n      bound: 2 rounds\n    needs: [spec]")


def test_on_fail_retries_the_stage_until_its_bound_then_escalates():
    state, _ = started(RETRY)
    state, _ = run(state, *THROUGH_SPEC)
    state, acts = run(state, failed("build"), failed("build"), failed("build"))
    assert [a["round"] for a in of(acts[0], "start-stage")] == [2]
    assert [a["round"] for a in of(acts[1], "start-stage")] == [3]
    assert dos(acts[2]) == ["escalate"] and acts[2][0]["to"] == "lead"


def test_on_fail_to_an_upstream_stage_reruns_everything_in_between():
    text = RETRY.replace("to: build", "to: spec")
    state, _ = started(text)
    state, _ = run(state, *THROUGH_SPEC)
    state, acts = run(state, failed("build"))
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["spec"]
    assert state["stages"]["build"]["status"] == "pending"


def test_a_loop_exit_predicate_that_is_false_runs_another_round():
    text = SWE.replace("      kind: verdict\n", "      policy: ship-it\n")
    state = at_review(text, policy={"ship-it": False})
    state, acts = run(state, done("review"))
    assert [a["round"] for a in of(acts[0], "start-stage")] == [2]


def test_a_loop_exit_predicate_that_is_true_leaves_the_loop():
    text = SWE.replace("      kind: verdict\n", "      policy: ship-it\n")
    state = at_review(text, policy={"ship-it": True})
    state, acts = run(state, done("review"))
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["integrate"]
