import pytest
from procedure_testkit import step
from runtime_fixtures import SWE, dos, done, fresh, of, run, started

# review runs only when the change touches auth code
SEC = SWE.replace(
    "  integrate:\n",
    "  audit:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [report]\n    metrics: [m]\n"
    "    when:\n      paths: [src/auth/**, infra/*]\n  integrate:\n",
).replace("    needs: [review]\n    consumes: [verdict]\n    produces: [merged]", "    needs: [review]\n    consumes: [verdict]\n    produces: [merged]")


def begin(text=SEC, changed=None, **kw):
    state = fresh(text, **kw)
    event = {"type": "run-started"}
    if changed is not None:
        event["changed"] = changed
    return run(state, event)


def through_build(state):
    state, acts = run(state, done("align"), done("spec"), done("build"))
    return state, acts[-1]


def test_a_stage_whose_paths_match_the_change_runs():
    state, _ = begin(changed=["src/auth/login.py"])
    state, acts = through_build(state)
    assert {a["stage"] for a in of(acts, "start-stage")} == {"review", "audit"}


def test_a_stage_whose_paths_do_not_match_is_skipped_and_does_not_block_the_run():
    state, _ = begin(changed=["docs/readme.md"])
    state, acts = through_build(state)
    assert {a["stage"] for a in of(acts, "start-stage")} == {"review"}
    assert state["stages"]["audit"]["status"] == "skipped"
    state, acts = run(state, done("review"), done("integrate", {"merged": "sha://z"}))
    assert state["status"] == "done"


def test_a_skipped_stage_is_recorded_so_the_skip_is_visible():
    state, _ = begin(changed=["docs/readme.md"])
    state, acts = through_build(state)
    assert {"do": "stage-skipped", "stage": "audit", "why": "when not met"} in acts


def test_the_change_list_is_recorded_once_at_the_start():
    state, _ = begin(changed=["a", "b"])
    assert state["changed"] == ["a", "b"]


def test_a_run_started_without_a_change_list_skips_every_path_conditional_stage():
    state, _ = begin()
    state, acts = through_build(state)
    assert state["stages"]["audit"]["status"] == "skipped"


@pytest.mark.parametrize("bad", ["src/auth/x.py", [1, 2], {"a": "b"}])
def test_a_malformed_change_list_is_rejected(bad):
    state, acts = run(fresh(SEC), {"type": "run-started", "changed": bad})
    assert dos(acts[0]) == ["error"]


def test_a_stage_with_a_policy_predicate_follows_the_policy():
    text = SEC.replace("      paths: [src/auth/**, infra/*]\n", "      policy: security\n")
    on, _ = begin(text, policy={"security": True})
    on, acts = through_build(on)
    assert "audit" in {a["stage"] for a in of(acts, "start-stage")}
    off, _ = begin(text, policy={"security": False})
    off, acts = through_build(off)
    assert off["stages"]["audit"]["status"] == "skipped"


def test_a_stage_with_a_kind_predicate_runs_only_when_that_kind_exists():
    text = SEC.replace("      paths: [src/auth/**, infra/*]\n", "      kind: change\n")
    state, _ = begin(text)
    state, acts = through_build(state)
    assert "audit" in {a["stage"] for a in of(acts, "start-stage")}


def test_all_predicates_in_a_when_must_hold():
    text = SEC.replace("      paths: [src/auth/**, infra/*]\n", "      paths: [src/auth/**]\n      policy: security\n")
    state, _ = begin(text, changed=["src/auth/x.py"], policy={"security": False})
    state, acts = through_build(state)
    assert state["stages"]["audit"]["status"] == "skipped"


def test_a_stage_that_waits_on_a_skipped_stage_still_runs():
    text = SEC.replace("    needs: [review]\n    consumes: [verdict]\n    produces: [merged]", "    needs: [review, audit]\n    consumes: [verdict]\n    produces: [merged]")
    state, _ = begin(text, changed=["docs/x.md"])
    state, _ = through_build(state)
    state, acts = run(state, done("review"))
    assert [a["stage"] for a in of(acts[0], "start-stage")] == ["integrate"]


def test_replay_of_a_run_with_skips_is_exact():
    from procedure_testkit import replay
    events = [{"type": "run-started", "changed": ["docs/x.md"]}, done("align"), done("spec"), done("build"), done("review"), done("integrate")]
    a, b = replay(SEC, events), replay(SEC, events)
    assert a == b and a[0]["status"] == "done"
