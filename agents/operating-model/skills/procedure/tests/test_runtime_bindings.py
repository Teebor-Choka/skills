import json

import pytest
from procedure_testkit import step
from runtime_fixtures import SWE, dos, done, fresh, of, run, started
from metrics_fixtures import MET, delta, item_of, propose, run_with, approve

TOP = "policy:\n  work.tracker: where issues live\n  vcs.remote: where to push\n  comms.channel: how nodes talk\n"
BOUND = SWE.replace("kpis:", TOP + "kpis:", 1).replace(
    "  align:\n    entity: pm\n    produces: [brief]\n",
    "  align:\n    entity: pm\n    produces: [brief]\n    uses: [work.tracker, comms.channel]\n", 1)
VALUES = {"work.tracker": "github", "vcs.remote": "origin", "comms.channel": "slack:#a", "unrelated": "x"}


def test_a_run_needs_a_value_for_every_declared_key():
    with pytest.raises(ValueError, match="vcs.remote"):
        fresh(BOUND, bindings={"work.tracker": "github", "comms.channel": "c"})
    with pytest.raises(ValueError, match="work.tracker"):
        fresh(BOUND)


def test_only_the_declared_keys_are_kept_in_the_state():
    state = fresh(BOUND, bindings=VALUES)
    assert state["bindings"] == {"work.tracker": "github", "vcs.remote": "origin", "comms.channel": "slack:#a"}


def test_a_stage_is_told_only_the_keys_it_uses():
    state, acts = started(BOUND, bindings=VALUES)
    start = of(acts, "start-stage")[0]
    assert start["uses"] == {"work.tracker": "github", "comms.channel": "slack:#a"}
    state, acts = run(state, done("align"))
    assert of(acts[0], "start-stage")[0]["uses"] == {}


def test_the_bindings_survive_json():
    state = fresh(BOUND, bindings=VALUES)
    assert json.loads(json.dumps(state))["bindings"] == state["bindings"]


def test_a_procedure_with_no_declared_keys_needs_no_bindings():
    assert fresh(SWE)["bindings"] == {}


@pytest.mark.parametrize("bad", [{"work.tracker": ""}, {"work.tracker": None}, {"work.tracker": "  "}])
def test_an_empty_value_is_not_a_binding(bad):
    with pytest.raises(ValueError, match="work.tracker"):
        fresh(BOUND, bindings={**VALUES, **bad})


def test_the_revision_is_recorded_on_the_run_and_on_the_first_snapshot():
    rev = {"project": "abc1234", "user": None, "dirty": False}
    state = fresh(SWE, revision=rev)
    assert state["revision"] == rev and state["snapshots"][0]["revision"] == rev


def test_a_run_with_no_revision_says_so():
    assert fresh(SWE)["revision"] is None


def test_an_amendment_that_needs_a_policy_key_nothing_set_is_refused():
    state, _ = started(MET.replace("kpis:", TOP + "kpis:", 1), bindings=VALUES)
    body = "policy:\n  report.sink: where reports go\nstages:\n  lint:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [lint-report]\n    metrics: [rework]\n    uses: [report.sink]\n"
    state, acts = run_with(propose(delta(body)), state=state)
    assert dos(acts[0]) == ["error"] and "report.sink" in acts[0][0]["reason"]


def test_an_amendment_that_uses_a_key_already_set_is_accepted():
    state, _ = started(MET.replace("kpis:", TOP + "kpis:", 1), bindings=VALUES)
    body = "stages:\n  lint:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [lint-report]\n    metrics: [rework]\n    uses: [vcs.remote]\n"
    state, acts = run_with(propose(delta(body)), state=state)
    assert dos(acts[0]) == ["notify-owner"]
