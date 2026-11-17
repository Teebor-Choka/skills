import pytest
from runtime_fixtures import LOCATORS, SWE
from signed_fixtures import sfresh

from executor import KeyRing, drive, new_ring, resume
from ledger import Ledger, LedgerError, assurance_of, recover
from procedure_testkit import new_state

KEY = b"executor-ledger-key-32-bytes-long!"
ALLOW = lambda event: True  # noqa: E731


class Claims:
    """A no-signing executor: each stage reports itself done with no signature."""

    def run(self, action):
        if action["do"] != "start-stage":
            return []
        return [{"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]}]


class Signed:
    def __init__(self, ring):
        self.ring = ring

    def run(self, action):
        if action["do"] != "start-stage":
            return []
        who = self.ring.issue(action["entity"])
        return [who.seal({"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]})]


def claims_run(tmp_path, max_steps=1000):
    state = new_state(SWE)
    ledger = Ledger(tmp_path / "c.ledger", KEY)
    return drive(state, Claims(), None, verify_owner=ALLOW, ledger=ledger, max_steps=max_steps), ledger


def signed_run(tmp_path, max_steps=1000):
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "s.ledger", KEY)
    return drive(state, Signed(ring), ring, verify_owner=ALLOW, ledger=ledger, max_steps=max_steps), ledger


# ---- a run with no signing can be driven and is labelled

def test_a_run_with_no_signing_is_driven_to_the_end_without_a_key_ring(tmp_path):
    out, _ = claims_run(tmp_path)
    assert out.status == "done"


def test_the_header_records_the_signing_mode(tmp_path):
    _, c = claims_run(tmp_path)
    _, s = signed_run(tmp_path)
    assert c.read()[0]["body"]["trust"] == "claims" and s.read()[0]["body"]["trust"] == "signed"


def test_every_event_entry_carries_the_signing_mode(tmp_path):
    _, c = claims_run(tmp_path)
    _, s = signed_run(tmp_path)
    assert {e["body"]["signing"] for e in c.read() if e["kind"] == "event"} == {"none"}
    assert {e["body"]["signing"] for e in s.read() if e["kind"] == "event"} == {"signed"}


def test_an_unsigned_entry_never_names_an_identity(tmp_path):
    _, c = claims_run(tmp_path)
    assert {e["body"]["by"] for e in c.read() if e["kind"] == "event"} == {"unverified"}


def test_assurance_of_a_signed_ledger_is_signed_and_of_an_unsigned_one_is_none(tmp_path):
    _, c = claims_run(tmp_path)
    _, s = signed_run(tmp_path)
    assert assurance_of(s.read()) == "signed" and assurance_of(c.read()) == "none"


def test_one_unsigned_entry_makes_the_whole_ledger_none(tmp_path):
    _, s = signed_run(tmp_path)
    entries = s.read()
    entries[3] = {**entries[3], "body": {**entries[3]["body"], "signing": "none"}}
    assert assurance_of(entries) == "none"


def test_a_ledger_with_no_header_has_no_assurance():
    assert assurance_of([]) == "none"


def test_a_no_signing_ledger_recovers_to_the_state_the_run_ended_in(tmp_path):
    out, ledger = claims_run(tmp_path)
    state = recover(ledger)
    assert state["status"] == "done" and state["log"] == out.state["log"] and state["trust"] == "claims"


def test_a_no_signing_run_is_resumed_without_a_ring(tmp_path):
    out, ledger = claims_run(tmp_path, max_steps=4)
    assert out.status == "exhausted"
    assert new_ring(Ledger(ledger.path, KEY)) is None
    done = resume(Ledger(ledger.path, KEY), Claims(), None, verify_owner=ALLOW)
    assert done.status == "done"


# ---- the mode and the ring must agree

def test_a_signed_run_needs_a_ring():
    with pytest.raises(ValueError, match="ring"):
        drive(sfresh(), Claims(), None, verify_owner=ALLOW)


def test_a_signed_resume_needs_a_ring(tmp_path):
    _, ledger = signed_run(tmp_path, max_steps=4)
    with pytest.raises(ValueError, match="ring"):
        resume(Ledger(ledger.path, KEY), Claims(), None, verify_owner=ALLOW)


def test_a_ring_given_to_a_no_signing_run_is_ignored_not_trusted(tmp_path):
    state = new_state(SWE)
    ring = KeyRing(state["run_id"], ["pm"])
    ledger = Ledger(tmp_path / "l", KEY)
    out = drive(state, Claims(), ring, verify_owner=ALLOW, ledger=ledger)
    assert out.status == "done" and assurance_of(ledger.read()) == "none"


def test_a_header_that_says_no_signing_makes_the_ledger_none_whatever_the_entries_say(tmp_path):
    _, s = signed_run(tmp_path)
    entries = s.read()
    entries[0] = {**entries[0], "body": {**entries[0]["body"], "trust": "claims"}}
    assert assurance_of(entries) == "none"


def test_a_ring_given_to_a_no_signing_run_names_no_identity(tmp_path):
    state = new_state(SWE)
    ring = KeyRing(state["run_id"], ["pm"])
    ledger = Ledger(tmp_path / "l", KEY)
    drive(state, Claims(), ring, verify_owner=ALLOW, ledger=ledger)
    assert {e["body"]["by"] for e in ledger.read() if e["kind"] == "event"} == {"unverified"}


def test_resume_ignores_a_ring_for_another_run_when_the_run_has_no_signing(tmp_path):
    out, ledger = claims_run(tmp_path, max_steps=4)
    done = resume(Ledger(ledger.path, KEY), Claims(), KeyRing("another-run", ["pm"]), verify_owner=ALLOW)
    assert done.status == "done"
