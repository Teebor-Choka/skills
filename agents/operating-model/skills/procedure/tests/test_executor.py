import pytest
from procedure_testkit import step
from runtime_fixtures import LOCATORS, SWE, dos, of
from signed_fixtures import STAGE_ENTITY, sfresh

from executor import Identity, KeyRing, Outcome, drive

OWNER_OK = lambda event: False  # noqa: E731  (no owner decision is ever valid)


def ring_for(state):
    return KeyRing(state["run_id"], entities=state["proc"]["entities"])


class Scripted:
    """An in-context executor: runs each start-stage as the stage's own entity and reports it done."""

    def __init__(self, ring, fail=(), forge=None):
        self.ring, self.seen, self.forge = ring, [], forge

    def run(self, action):
        self.seen.append(action["do"])
        if action["do"] != "start-stage":
            return []
        sid = action["stage"]
        who = self.forge or action["entity"]
        who = self.ring.issue(who)
        return [who.seal({"type": "stage-done", "stage": sid, "round": action["round"], "locators": LOCATORS[sid]})]


def driven(**kw):
    state = sfresh()
    ring = ring_for(state)
    ex = kw.pop("executor", None) or Scripted(ring)
    return drive(state, ex, ring, verify_owner=OWNER_OK, **kw), ring, ex


# ---- key custody

def test_an_identity_seals_events_the_ring_verifies_as_that_entity():
    ring = ring_for(sfresh())
    event = ring.issue("worker").seal({"type": "stage-done", "stage": "build"})
    assert ring.verify_sender({**event, "run_id": "run"}) == "worker"


def test_each_issue_is_a_fresh_instance_with_its_own_secret():
    ring = ring_for(sfresh())
    one, two = ring.issue("worker"), ring.issue("worker")
    assert one.instance != two.instance
    a = one.seal({"type": "t"})
    b = two.seal({"type": "t"})
    assert a["signature"] != b["signature"]


def test_a_sealed_event_cannot_be_retargeted_to_another_entity():
    ring = ring_for(sfresh())
    event = ring.issue("worker").seal({"type": "stage-done", "stage": "build"})
    assert ring.verify_sender({**event, "sender": "pm", "run_id": "run"}) is None


def test_a_tampered_body_or_another_run_fails_verification():
    ring = ring_for(sfresh())
    event = ring.issue("worker").seal({"type": "stage-done", "stage": "build"})
    assert ring.verify_sender({**event, "stage": "review", "run_id": "run"}) is None
    assert ring.verify_sender({**event, "run_id": "other"}) is None


def test_an_unknown_instance_or_a_revoked_one_is_refused():
    ring = ring_for(sfresh())
    who = ring.issue("worker")
    event = who.seal({"type": "t"})
    assert ring.verify_sender({**event, "instance": "nope", "run_id": "run"}) is None
    ring.revoke(who.instance)
    assert ring.verify_sender({**event, "run_id": "run"}) is None


def test_only_entities_of_the_procedure_get_an_identity():
    with pytest.raises(ValueError, match="entity"):
        ring_for(sfresh()).issue("intruder")


def test_the_executor_key_is_separate_from_every_entity_key():
    ring = ring_for(sfresh())
    fact = ring.executor_event({"type": "run-started"})
    assert ring.verify_executor({**fact, "run_id": "run"}) is True
    assert ring.verify_sender({**fact, "run_id": "run"}) is None
    forged = ring.issue("pm").seal({"type": "run-started"})
    assert ring.verify_executor({**forged, "run_id": "run"}) is False


def test_an_identity_does_not_show_its_secret():
    ring = ring_for(sfresh())
    who = ring.issue("worker")
    assert isinstance(who, Identity)
    event = who.seal({"type": "t"})
    assert event["signature"] not in repr(who) and "key" not in repr(who).lower().replace("keyring", "")


# ---- the drive loop

def test_drive_runs_a_signed_procedure_to_completion():
    out, ring, ex = driven()
    assert isinstance(out, Outcome) and out.status == "done" and out.state["status"] == "done"
    assert [e["stage"] for e in out.state["log"] if e["type"] == "stage-done"] == list(STAGE_ENTITY)


def test_an_event_forged_for_another_entitys_stage_moves_nothing():
    state = sfresh()
    ring = ring_for(state)
    out = drive(state, Scripted(ring, forge="worker"), ring, verify_owner=OWNER_OK)
    assert out.status == "stalled" and out.state["stages"]["align"]["status"] == "running"
    assert out.errors and "sender" in out.errors[0]["reason"]


def test_drive_stops_waiting_when_the_run_needs_the_owner():
    class Blocks(Scripted):
        def run(self, action):
            if action["do"] == "start-stage" and action["stage"] == "review":
                who = self.ring.issue(action["entity"])
                return [who.seal({"type": "stage-failed", "stage": "review", "round": action["round"],
                                  "reason": "defects", "locators": {}})]
            return super().run(action)

    state = sfresh()
    ring = ring_for(state)
    out = drive(state, Blocks(ring), ring, verify_owner=OWNER_OK, max_steps=200)
    assert out.status in ("waiting", "exhausted", "stalled") and out.state["status"] != "done"


def test_drive_is_bounded_when_an_executor_never_settles():
    class Echo:
        def __init__(self, ring):
            self.ring = ring

        def run(self, action):
            return [self.ring.executor_event({"type": "run-started"})]  # refused every time

    state = sfresh()
    ring = ring_for(state)
    out = drive(state, Echo(ring), ring, verify_owner=OWNER_OK, max_steps=25)
    assert out.status in ("exhausted", "stalled") and len(out.actions) <= 25 + 5


def test_an_executor_that_raises_ends_the_drive_with_a_reason_not_a_crash():
    class Boom:
        def run(self, action):
            raise RuntimeError("spawn failed")

    state = sfresh()
    ring = ring_for(state)
    out = drive(state, Boom(), ring, verify_owner=OWNER_OK)
    assert out.status == "failed" and "spawn failed" in out.errors[-1]["reason"]


def test_two_executors_that_do_the_same_work_yield_the_same_log():
    a, _, _ = driven()

    class Team(Scripted):  # same decisions, one extra hop through a queue
        def run(self, action):
            queued = list(super().run(action))
            return queued

    state = sfresh()
    ring = ring_for(state)
    b = drive(state, Team(ring), ring, verify_owner=OWNER_OK)
    strip = lambda o: [(e["type"], e.get("stage")) for e in o.state["log"]]  # noqa: E731
    assert strip(a) == strip(b) and dos(a.actions) == dos(b.actions)


def test_drive_refuses_a_run_that_is_not_new():
    state = sfresh()
    ring = ring_for(state)
    done = drive(state, Scripted(ring), ring, verify_owner=OWNER_OK).state
    with pytest.raises(ValueError, match="new"):
        drive(done, Scripted(ring), ring, verify_owner=OWNER_OK)


def test_drive_refuses_a_claims_run():
    from signed_fixtures import new_state
    state = new_state(SWE)
    with pytest.raises(ValueError, match="signed"):
        drive(state, Scripted(ring_for(sfresh())), ring_for(sfresh()), verify_owner=OWNER_OK)


def test_drive_stops_at_the_step_bound_even_when_work_remains():
    out, _, _ = driven(max_steps=2)
    assert out.status == "exhausted" and out.state["status"] != "done"
