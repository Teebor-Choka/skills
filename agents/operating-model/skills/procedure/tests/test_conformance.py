import json
from pathlib import Path

import pytest
from runtime_fixtures import LOCATORS, SWE
from signed_fixtures import sfresh

from conformance import check_ledger
from executor import KeyRing, drive
from ledger import Ledger
from procedure_testkit import new_state

KEY = b"executor-ledger-key-32-bytes-long!"
ALLOW = lambda event: True  # noqa: E731


class Signed:
    def __init__(self, ring):
        self.ring = ring

    def run(self, action):
        if action["do"] != "start-stage":
            return []
        return [self.ring.issue(action["entity"]).seal({"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]})]


class Claims:
    def run(self, action):
        if action["do"] != "start-stage":
            return []
        return [{"type": "stage-done", "stage": action["stage"], "round": action["round"], "locators": LOCATORS[action["stage"]]}]


def signed(tmp_path):
    state = sfresh()
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ledger = Ledger(tmp_path / "s", KEY)
    return drive(state, Signed(ring), ring, verify_owner=ALLOW, ledger=ledger).state, ledger


def unsigned(tmp_path):
    ledger = Ledger(tmp_path / "u", KEY)
    return drive(new_state(SWE), Claims(), None, verify_owner=ALLOW, ledger=ledger).state, ledger


def rewrite(ledger, edit):
    """Change an entry and re-sign the chain, as a ledger writer with the key could."""
    entries = ledger.read()
    edit(entries)
    path = Path(ledger.path)
    path.unlink()
    out = Ledger(path, KEY)
    for e in entries:
        out.append(e["kind"], e["body"])
    return out


def test_a_conforming_signed_ledger_has_no_violations(tmp_path):
    state, ledger = signed(tmp_path)
    assert check_ledger(ledger, state) == []


def test_a_conforming_unsigned_ledger_has_no_violations(tmp_path):
    state, ledger = unsigned(tmp_path)
    assert check_ledger(ledger, state) == []


def test_a_ledger_that_does_not_replay_to_the_final_state_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    state = {**state, "status": "halted"}
    assert any("replay" in v for v in check_ledger(ledger, state))


def test_a_missing_header_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    ledger = rewrite(ledger, lambda e: e.pop(0))
    assert any("header" in v for v in check_ledger(ledger, state))


def test_an_event_entry_with_no_signing_label_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    ledger = rewrite(ledger, lambda e: e[2]["body"].pop("signing"))
    assert any("signing" in v for v in check_ledger(ledger, state))


def test_a_signed_run_with_an_unsigned_entry_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    ledger = rewrite(ledger, lambda e: e[2]["body"].update(signing="none"))
    assert any("signed run" in v for v in check_ledger(ledger, state))


def test_an_unsigned_run_that_names_an_identity_is_a_violation(tmp_path):
    state, ledger = unsigned(tmp_path)
    ledger = rewrite(ledger, lambda e: e[2]["body"].update(by="pm"))
    assert any("unverified" in v for v in check_ledger(ledger, state))


def test_a_signed_run_that_leaves_an_entry_unverified_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    ledger = rewrite(ledger, lambda e: e[2]["body"].update(by="unverified"))
    assert any("unverified" in v for v in check_ledger(ledger, state))


def test_a_broken_chain_is_reported_not_raised(tmp_path):
    state, ledger = signed(tmp_path)
    lines = Path(ledger.path).read_text().splitlines()
    Path(ledger.path).write_text("\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n")
    assert any("chain" in v for v in check_ledger(Ledger(ledger.path, KEY), state))


def test_a_ledger_whose_header_trust_disagrees_with_the_state_is_a_violation(tmp_path):
    state, ledger = signed(tmp_path)
    assert any("trust" in v for v in check_ledger(ledger, {**state, "trust": "claims"}))


def test_the_check_runs_from_the_command_line(tmp_path, capsys):
    from conformance import main
    state, ledger = signed(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps(state))
    assert main([str(ledger.path), "--key", KEY.decode(), "--state", str(tmp_path / "state.json")]) == 0
    state["status"] = "halted"
    (tmp_path / "state.json").write_text(json.dumps(state))
    assert main([str(ledger.path), "--key", KEY.decode(), "--state", str(tmp_path / "state.json")]) == 1
    assert "replay" in capsys.readouterr().err
