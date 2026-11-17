import copy

import pytest
from procedure_testkit import step
from runtime import pending_actions
from runtime_fixtures import LOCATORS
from signed_fixtures import sfresh

from executor import KeyRing, drive, new_ring, resume
from ledger import Ledger, LedgerError, recover

KEY = b"executor-ledger-key-32-bytes-long!"
ALLOW = lambda event: True  # noqa: E731


class Scripted:
    """Runs each start-stage as the stage's own entity. `fail_once` makes that stage fail on its first run."""

    def __init__(self, ring, fail_once=None, seen=None):
        self.ring, self.fail_once, self.seen = ring, fail_once, seen if seen is not None else []
        self.failed = False

    def run(self, action):
        self.seen.append((action["do"], action.get("stage") or action.get("item"), action.get("round")))
        if action["do"] != "start-stage":
            return []
        who = self.ring.issue(action["entity"])
        if action["stage"] == self.fail_once and not self.failed:
            self.failed = True
            return [who.seal({"type": "stage-failed", "stage": action["stage"], "round": action["round"], "reason": "r", "locators": {}})]
        return [who.seal({"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]})]


def crashed(tmp_path, max_steps=3, **kw):
    """A run that stopped after a few steps, as a crash would leave it."""
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "run.ledger", KEY)
    out = drive(state, Scripted(ring, **kw), ring, verify_owner=ALLOW, ledger=ledger, max_steps=max_steps)
    return out, ledger, ring


def reopened(ledger):
    return Ledger(ledger.path, KEY)


# ---- pending_actions

def test_pending_actions_lists_each_running_stage_and_changes_nothing():
    out, _, _ = crashed_state()
    before = copy.deepcopy(out.state)
    acts = pending_actions(out.state)
    assert out.state == before
    running = [s for s, st in out.state["stages"].items() if st["status"] == "running"]
    assert [a["stage"] for a in acts if a["do"] == "start-stage"] == running and running


def crashed_state():
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    return drive(state, Scripted(ring), ring, verify_owner=ALLOW, max_steps=3), None, ring


def test_a_pending_start_carries_the_same_round_inputs_and_entity_as_the_original():
    out, _, _ = crashed_state()
    start = next(a for a in pending_actions(out.state) if a["do"] == "start-stage")
    spec = out.state["proc"]["stages"][start["stage"]]
    assert start["round"] == out.state["stages"][start["stage"]].get("round", 1) and start["entity"] == spec["entity"]
    assert start["inputs"] and start["verify"] is True


def test_a_finished_run_has_no_pending_actions():
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    out = drive(state, Scripted(ring), ring, verify_owner=ALLOW)
    assert out.status == "done" and pending_actions(out.state) == []


def test_an_open_item_is_pending_again_for_whoever_holds_it():
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    out = drive(state, Scripted(ring, fail_once="align"), ring, verify_owner=ALLOW)
    acts = pending_actions(out.state)
    assert [a["do"] for a in acts] == ["notify-owner"] and acts[0]["item"] == out.state["items"][0]["id"]


# ---- resume

def test_a_crashed_run_is_resumed_to_the_end(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    assert out.status == "exhausted"
    ring = new_ring(reopened(ledger))
    done = resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW)
    assert done.status == "done" and all(s["status"] == "done" for s in done.state["stages"].values())


def test_resume_hands_the_executor_each_stage_that_was_running_with_its_round(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    running = {s: st.get("round", 1) for s, st in out.state["stages"].items() if st["status"] == "running"}
    seen = []
    ring = new_ring(reopened(ledger))
    resume(reopened(ledger), Scripted(ring, seen=seen), ring, verify_owner=ALLOW)
    assert {(s, r) for d, s, r in seen[: len(running)] if d == "start-stage"} == set(running.items())


def test_the_resumed_ledger_recovers_to_the_state_the_resume_ended_in(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    ring = new_ring(reopened(ledger))
    done = resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW)
    again = recover(reopened(ledger))
    assert again["status"] == "done" and again["log"] == done.state["log"] and again["stages"] == done.state["stages"]


def test_a_resume_is_marked_in_the_ledger(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    ring = new_ring(reopened(ledger))
    resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW)
    assert any(e["kind"] == "resume" for e in reopened(ledger).read())


def test_a_waiting_run_is_renotified_and_continues_on_an_owner_decision_that_arrived_while_down(tmp_path):
    out, ledger, _ = crashed(tmp_path, max_steps=1000, fail_once="align")
    assert out.status == "waiting"
    item = out.state["items"][0]["id"]
    seen = []
    ring = new_ring(reopened(ledger))
    decision = {"type": "owner-decided", "item": item, "decision": "retry", "signature": "sig"}
    done = resume(reopened(ledger), Scripted(ring, seen=seen), ring, verify_owner=ALLOW, events=[decision])
    assert ("notify-owner", item, None) in seen and done.status == "done"


def test_an_identity_from_before_the_crash_is_dead_after_the_resume(tmp_path):
    out, ledger, old_ring = crashed(tmp_path)
    stage = next(s for s, st in out.state["stages"].items() if st["status"] == "running")
    entity = out.state["proc"]["stages"][stage]["entity"]
    late = old_ring.issue(entity).seal({"type": "stage-done", "stage": stage, "round": out.state["stages"][stage].get("round", 1), "locators": LOCATORS[stage]})
    ring = new_ring(reopened(ledger))
    seen = []
    done = resume(reopened(ledger), Scripted(ring, seen=seen), ring, verify_owner=ALLOW, events=[late])
    assert ("start-stage", stage, out.state["stages"][stage].get("round", 1)) in seen  # the stage was still open to be done again
    assert done.status == "done" and sum(1 for e in done.state["log"] if e.get("signature") == late["signature"]) == 0


def test_a_torn_ledger_tail_does_not_stop_a_resume(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    with open(ledger.path, "a") as f:
        f.write('{"seq": 99, "pr')
    ring = new_ring(reopened(ledger))
    assert resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW).status == "done"
    assert recover(reopened(ledger))["status"] == "done"


def test_resume_on_a_finished_run_changes_nothing_and_asks_the_executor_for_nothing(tmp_path):
    out, ledger, _ = crashed(tmp_path, max_steps=1000)
    assert out.status == "done"
    ring = new_ring(reopened(ledger))
    seen = []
    again = resume(reopened(ledger), Scripted(ring, seen=seen), ring, verify_owner=ALLOW)
    assert again.status == "done" and seen == []


def test_resume_is_bounded_like_drive(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    ring = new_ring(reopened(ledger))
    assert resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW, max_steps=1).status == "exhausted"


def test_resume_refuses_a_ring_for_another_run(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    with pytest.raises(ValueError, match="run"):
        resume(reopened(ledger), Scripted(None), KeyRing("another-run", ["pm"]), verify_owner=ALLOW)


def test_resume_refuses_a_ledger_that_never_started_the_run(tmp_path):
    ledger = Ledger(tmp_path / "l", KEY)
    state = sfresh()
    from ledger import header_of
    ledger.append("header", header_of(state))
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    with pytest.raises(ValueError, match="started"):
        resume(ledger, Scripted(ring), ring, verify_owner=ALLOW)


def test_resume_refuses_a_tampered_ledger(tmp_path):
    out, ledger, _ = crashed(tmp_path)
    lines = open(ledger.path).read().splitlines()
    lines[2] = lines[2].replace('"stage":"align"', '"stage":"build"')
    open(ledger.path, "w").write("\n".join(lines) + "\n")
    with pytest.raises(LedgerError):
        new_ring(reopened(ledger))


def test_a_run_can_be_resumed_twice(tmp_path):
    out, ledger, _ = crashed(tmp_path, max_steps=3)
    ring = new_ring(reopened(ledger))
    mid = resume(reopened(ledger), Scripted(ring), ring, verify_owner=ALLOW, max_steps=4)
    assert mid.status == "exhausted"
    ring2 = new_ring(reopened(ledger))
    assert resume(reopened(ledger), Scripted(ring2), ring2, verify_owner=ALLOW).status == "done"
