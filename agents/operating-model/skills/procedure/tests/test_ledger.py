from pathlib import Path

import pytest
from runtime_fixtures import LOCATORS, SWE
from signed_fixtures import STAGE_ENTITY, sfresh

from executor import KeyRing, drive
from ledger import GENESIS, Ledger, LedgerError, recover

KEY = b"executor-ledger-key-32-bytes-long!"
OWNER_OK = lambda event: False  # noqa: E731


class Scripted:
    def __init__(self, ring):
        self.ring = ring

    def run(self, action):
        if action["do"] != "start-stage":
            return []
        who = self.ring.issue(action["entity"])
        return [who.seal({"type": "stage-done", "stage": action["stage"], "round": action["round"],
                          "locators": LOCATORS[action["stage"]]})]


def driven(tmp_path, stop_after=None):
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "run.ledger", KEY)
    out = drive(state, Scripted(ring), ring, verify_owner=OWNER_OK, ledger=ledger, max_steps=stop_after or 1000)
    return out, ledger


# ---- the chain

def test_entries_chain_from_a_genesis_value(tmp_path):
    ledger = Ledger(tmp_path / "l", KEY)
    a = ledger.append("note", {"n": 1})
    b = ledger.append("note", {"n": 2})
    assert a["prev"] == GENESIS and b["prev"] == a["mac"] and (a["seq"], b["seq"]) == (1, 2)


def test_a_ledger_reopened_continues_the_chain(tmp_path):
    first = Ledger(tmp_path / "l", KEY)
    a = first.append("note", {"n": 1})
    b = Ledger(tmp_path / "l", KEY).append("note", {"n": 2})
    assert b["prev"] == a["mac"] and b["seq"] == 2


def test_read_returns_the_entries_in_order(tmp_path):
    ledger = Ledger(tmp_path / "l", KEY)
    for n in range(3):
        ledger.append("note", {"n": n})
    assert [e["body"]["n"] for e in ledger.read()] == [0, 1, 2]


@pytest.mark.parametrize("edit", [
    lambda lines: [lines[0].replace('"n":0', '"n":9')] + lines[1:],
    lambda lines: [lines[1], lines[0], lines[2]],
    lambda lines: [lines[0], lines[2]],
    lambda lines: lines[1:],
], ids=["edited", "reordered", "deleted-middle", "deleted-first"])
def test_any_change_in_the_middle_is_an_error(tmp_path, edit):
    path = tmp_path / "l"
    ledger = Ledger(path, KEY)
    for n in range(3):
        ledger.append("note", {"n": n})
    path.write_text("\n".join(edit(path.read_text().splitlines())) + "\n")
    with pytest.raises(LedgerError):
        Ledger(path, KEY).read()


def test_a_different_key_cannot_read_the_ledger(tmp_path):
    Ledger(tmp_path / "l", KEY).append("note", {"n": 1})
    with pytest.raises(LedgerError):
        Ledger(tmp_path / "l", b"another-key-another-key-another!").read()


def test_a_torn_last_line_is_dropped_and_reported_not_an_error(tmp_path):
    path = tmp_path / "l"
    ledger = Ledger(path, KEY)
    ledger.append("note", {"n": 1})
    with open(path, "a") as f:
        f.write('{"seq": 2, "prev": "ab')  # a crash mid-write
    reopened = Ledger(path, KEY)
    assert [e["seq"] for e in reopened.read()] == [1] and reopened.torn is True
    assert reopened.append("note", {"n": 2})["seq"] == 2  # the torn bytes are cut before the next write


def test_a_line_that_is_not_json_in_the_middle_is_an_error(tmp_path):
    path = tmp_path / "l"
    ledger = Ledger(path, KEY)
    ledger.append("note", {"n": 1})
    ledger.append("note", {"n": 2})
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], "not json", lines[1]]) + "\n")
    with pytest.raises(LedgerError):
        Ledger(path, KEY).read()


# ---- what drive records

def test_drive_records_a_header_then_every_applied_event(tmp_path):
    out, ledger = driven(tmp_path)
    entries = ledger.read()
    assert entries[0]["kind"] == "header" and entries[0]["body"]["run_id"] == out.state["run_id"]
    events = [e for e in entries if e["kind"] == "event"]
    assert [e["body"]["event"]["type"] for e in events] == [e["type"] for e in out.state["log"]]


def test_each_event_records_who_the_executor_verified_it_as(tmp_path):
    out, ledger = driven(tmp_path)
    by = {e["body"]["event"]["stage"]: e["body"]["by"] for e in ledger.read() if e["kind"] == "event" and e["body"]["event"]["type"] == "stage-done"}
    assert by == STAGE_ENTITY


def test_a_refused_event_is_not_recorded_as_applied(tmp_path):
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "l", KEY)

    class Forger(Scripted):
        def run(self, action):
            if action["do"] != "start-stage":
                return []
            return [self.ring.issue("worker").seal({"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]})]

    out = drive(state, Forger(ring), ring, verify_owner=OWNER_OK, ledger=ledger)
    assert out.status == "stalled"
    assert len([e for e in ledger.read() if e["kind"] == "event"]) == len(out.state["log"])


# ---- recovery

def test_recover_rebuilds_the_state_a_driven_run_ended_in(tmp_path):
    out, ledger = driven(tmp_path)
    state = recover(ledger)
    assert state["status"] == "done" == out.state["status"]
    assert state["stages"] == out.state["stages"] and state["log"] == out.state["log"]
    assert state["metrics"] == out.state["metrics"] and state["seen"] == out.state["seen"]


def test_recover_stops_at_a_torn_tail_with_the_state_before_it(tmp_path):
    out, ledger = driven(tmp_path)
    with open(ledger.path, "a") as f:
        f.write('{"seq": 99')
    reopened = Ledger(ledger.path, KEY)
    state = recover(reopened)
    assert state["log"] == out.state["log"] and reopened.torn is True


def test_recover_does_not_need_the_key_ring(tmp_path):
    out, ledger = driven(tmp_path)
    assert recover(Ledger(ledger.path, KEY))["status"] == "done"


def test_a_tampered_ledger_is_not_recovered(tmp_path):
    out, ledger = driven(tmp_path)
    path = Path(ledger.path)
    lines = path.read_text().splitlines()
    assert '"stage":"align"' in lines[2]
    lines[2] = lines[2].replace('"stage":"align"', '"stage":"build"')
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerError):
        recover(Ledger(ledger.path, KEY))


def test_recover_refuses_a_ledger_with_no_header(tmp_path):
    ledger = Ledger(tmp_path / "l", KEY)
    ledger.append("event", {"event": {"type": "run-started"}, "by": "executor"})
    with pytest.raises(LedgerError, match="header"):
        recover(ledger)


def test_the_ledger_is_still_valid_after_a_write_that_followed_a_torn_tail(tmp_path):
    path = tmp_path / "l"
    Ledger(path, KEY).append("note", {"n": 1})
    with open(path, "a") as f:
        f.write('{"seq": 2, "pr')
    reopened = Ledger(path, KEY)
    reopened.append("note", {"n": 2})
    assert [e["body"]["n"] for e in Ledger(path, KEY).read()] == [1, 2]


def test_recover_replays_an_owner_decision_the_executor_verified(tmp_path):
    class Escalates(Scripted):
        def __init__(self, ring):
            super().__init__(ring)
            self.failed = False

        def run(self, action):
            if action["do"] == "start-stage" and action["stage"] == "align" and not self.failed:
                self.failed = True
                return [self.ring.issue("pm").seal({"type": "stage-failed", "stage": "align", "round": action["round"], "reason": "r", "locators": {}})]
            if action["do"] == "notify-owner":
                return [{"type": "owner-decided", "item": action["item"], "decision": "retry", "signature": "owner-signature"}]
            return super().run(action)

    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "l", KEY)
    out = drive(state, Escalates(ring), ring, verify_owner=lambda e: True, ledger=ledger)
    assert any(i["status"] == "owner-ruled" for i in out.state["items"])
    recovered = recover(ledger)
    assert recovered["items"] == out.state["items"] and recovered["status"] == out.state["status"]
