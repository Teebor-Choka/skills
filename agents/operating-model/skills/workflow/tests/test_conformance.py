"""Acceptance tests for the operation contracts (U9) and the conformance harness.

Fakes live here, not in the harness: the harness takes any adapter with `call(op, input)`.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))

import conformance as cf  # noqa: E402
from conformance import PortError  # noqa: E402

CONTRACTS = SKILL / "contracts"
PORTS = ["Channel", "Tracker", "Documents", "Identity", "Instances", "Sessions", "Memory", "Metrics"]
OPS = {
    "Channel": ["send", "subscribe", "list-participants"],
    "Tracker": ["create-item", "update-item", "get-item", "search-items", "link-items"],
    "Documents": ["read", "write", "search", "share"],
    "Identity": ["issue", "revoke", "verify", "list"],
    "Instances": ["acquire", "release", "status"],
    "Sessions": ["export"],
    "Memory": ["recall", "remember", "forget"],
    "Metrics": ["observe", "query"],
}
PARTS = ["name", "input", "output", "requirements", "guarantees", "errors", "metrics"]
CATALOG = [
    "escalations", "spec-rework", "acceptance-coverage", "red-for-wrong-reason", "acceptance-rounds",
    "defects-found-in-review", "defects-escaped", "lead-time", "decision-latency", "write-set-collisions",
    "review-rounds", "report-complete", "proposals-accepted", "tests-per-unit", "diff-lines", "green-rounds",
]


def load(port):
    return json.loads((CONTRACTS / f"{port.lower()}.json").read_text())


# ---------------------------------------------------------------- fakes


class Fake:
    """Base: validates input against the contract schema, then dispatches to `op_<name>`."""

    def __init__(self, contract):
        self.contract = contract

    def call(self, op, inp):
        if cf.check_schema(inp, self.contract["operations"][op]["input"]):
            raise PortError("invalid-input", op)
        return getattr(self, "op_" + op.replace("-", "_"))(inp)


class FakeChannel(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.log = {}

    def op_send(self, i):
        log = self.log.setdefault(i["channel"], [])
        for m in log:
            if m["message_id"] == i["message_id"]:
                return {"message_id": m["message_id"], "seq": m["seq"], "duplicate": True}
        log.append({"seq": len(log) + 1, "message_id": i["message_id"], "sender": i["sender"], "text": i["text"]})
        return {"message_id": i["message_id"], "seq": len(log), "duplicate": False}

    def op_subscribe(self, i):
        msgs = [m for m in self.log.get(i["channel"], []) if m["seq"] > i.get("after", 0)]
        return {"messages": msgs, "cursor": msgs[-1]["seq"] if msgs else i.get("after", 0)}

    def op_list_participants(self, i):
        return {"participants": sorted({m["sender"] for m in self.log.get(i["channel"], [])})}


class FakeTracker(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.items, self.keys = {}, {}

    def op_create_item(self, i):
        if i["key"] in self.keys:
            return {"item_id": self.keys[i["key"]], "created": False}
        item_id = f"I{len(self.items) + 1}"
        self.keys[i["key"]] = item_id
        self.items[item_id] = {"item_id": item_id, "title": i["title"], "body": i.get("body", ""), "state": "open", "links": []}
        return {"item_id": item_id, "created": True}

    def _item(self, item_id):
        if item_id not in self.items:
            raise PortError("not-found", item_id)
        return self.items[item_id]

    def op_update_item(self, i):
        item = self._item(i["item_id"])
        item.update({k: v for k, v in i.items() if k != "item_id"})
        return {k: item[k] for k in ("item_id", "title", "body", "state")}

    def op_get_item(self, i):
        return copy.deepcopy(self._item(i["item_id"]))

    def op_search_items(self, i):
        hits = [it for it in self.items.values()
                if i.get("text", "") in it["title"] and i.get("state", it["state"]) == it["state"]]
        return {"items": [{k: h[k] for k in ("item_id", "title", "state")} for h in hits]}

    def op_link_items(self, i):
        a, b = self._item(i["from_id"]), self._item(i["to_id"])
        if b["item_id"] not in a["links"]:
            a["links"].append(b["item_id"])
        return {"linked": True}


class FakeDocuments(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.docs, self.shares = {}, {}

    def op_read(self, i):
        if i["path"] not in self.docs:
            raise PortError("not-found", i["path"])
        return {"path": i["path"], "content": self.docs[i["path"]]}

    def op_write(self, i):
        self.docs[i["path"]] = i["content"]
        return {"path": i["path"], "bytes": len(i["content"].encode())}

    def op_search(self, i):
        return {"paths": sorted(p for p, c in self.docs.items() if i["text"] in c)}

    def op_share(self, i):
        if i["path"] not in self.docs:
            raise PortError("not-found", i["path"])
        who = self.shares.setdefault(i["path"], [])
        if i["with"] not in who:
            who.append(i["with"])
        return {"path": i["path"], "shared_with": list(who)}


class FakeIdentity(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.creds, self.by_instance = {}, {}

    def op_issue(self, i):
        key = i["instance_id"]
        if key in self.by_instance:
            cred = self.creds[self.by_instance[key]]
            if (cred["kind"], cred["subject"]) != (i["kind"], i["subject"]):
                raise PortError("already-issued", key)
            return {k: cred[k] for k in ("credential_id", "instance_id", "kind", "subject")}
        cid = f"cred-{len(self.creds) + 1}"
        self.by_instance[key] = cid
        self.creds[cid] = {"credential_id": cid, "instance_id": key, "kind": i["kind"], "subject": i["subject"], "revoked": False}
        return {k: self.creds[cid][k] for k in ("credential_id", "instance_id", "kind", "subject")}

    def op_revoke(self, i):
        if i["credential_id"] not in self.creds:
            raise PortError("not-found", i["credential_id"])
        self.creds[i["credential_id"]]["revoked"] = True
        return {"credential_id": i["credential_id"], "revoked": True}

    def op_verify(self, i):
        cred = self.creds.get(i["credential_id"])
        if cred is None:
            return {"credential_id": i["credential_id"], "valid": False, "reason": "unknown"}
        return {"credential_id": i["credential_id"], "valid": not cred["revoked"], "reason": "revoked" if cred["revoked"] else "ok"}

    def op_list(self, i):
        return {"credentials": [dict(c) for c in self.creds.values() if i.get("include_revoked") or not c["revoked"]]}


class FakeInstances(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.boxes = {}

    def op_acquire(self, i):
        iid = f"inst-{len(self.boxes) + 1}"
        self.boxes[iid] = {"state": "running", "granted": copy.deepcopy(i)}
        return {"instance_id": iid, "granted": copy.deepcopy(i)}

    def op_release(self, i):
        if i["instance_id"] not in self.boxes:
            raise PortError("not-found", i["instance_id"])
        self.boxes[i["instance_id"]]["state"] = "released"
        return {"instance_id": i["instance_id"], "released": True}

    def op_status(self, i):
        if i["instance_id"] not in self.boxes:
            raise PortError("not-found", i["instance_id"])
        b = self.boxes[i["instance_id"]]
        return {"instance_id": i["instance_id"], "state": b["state"], "granted": copy.deepcopy(b["granted"])}


class FakeSessions(Fake):
    def op_export(self, i):
        if i["harness"] != "claude-code":
            raise PortError("unsupported-format", i["harness"])
        slices = i["native"]
        msgs = [{"role": s["type"], "text": s["text"]} for s in slices if s["type"] != "thinking"]
        return {"record": {"harness": i["harness"], "messages": msgs},
                "dropped_thinking": sum(1 for s in slices if s["type"] == "thinking")}


class FakeMemory(Fake):
    def __init__(self, contract):
        super().__init__(contract)
        self.kv = {}

    def op_remember(self, i):
        self.kv[i["key"]] = i["value"]
        return {"key": i["key"]}

    def op_recall(self, i):
        if i["key"] in self.kv:
            return {"found": True, "value": self.kv[i["key"]]}
        return {"found": False}

    def op_forget(self, i):
        return {"key": i["key"], "forgotten": self.kv.pop(i["key"], None) is not None}


class FakeMetrics(Fake):
    def __init__(self, contract, catalog=CATALOG):
        super().__init__(contract)
        self.catalog, self.seen, self.sums = set(catalog), set(), {}

    def op_observe(self, i):
        if i["metric"] not in self.catalog:
            raise PortError("unknown-metric", i["metric"])
        if i["observation_id"] in self.seen:
            return {"recorded": False}
        self.seen.add(i["observation_id"])
        count, total = self.sums.get(i["metric"], (0, 0))
        self.sums[i["metric"]] = (count + 1, total + i["value"])
        return {"recorded": True}

    def op_query(self, i):
        count, total = self.sums.get(i["metric"], (0, 0))
        return {"metric": i["metric"], "count": count, "sum": total}


FAKES = {
    "Channel": FakeChannel, "Tracker": FakeTracker, "Documents": FakeDocuments, "Identity": FakeIdentity,
    "Instances": FakeInstances, "Sessions": FakeSessions, "Memory": FakeMemory, "Metrics": FakeMetrics,
}


# ---------------------------------------------------------------- broken fakes: one violated guarantee each


class NonIdempotentSend(FakeChannel):
    def op_send(self, i):
        log = self.log.setdefault(i["channel"], [])
        log.append({"seq": len(log) + 1, "message_id": i["message_id"], "sender": i["sender"], "text": i["text"]})
        return {"message_id": i["message_id"], "seq": len(log), "duplicate": False}


class UnorderedSubscribe(FakeChannel):
    def op_subscribe(self, i):
        out = super().op_subscribe(i)
        out["messages"].reverse()
        return out


class DuplicatingCreate(FakeTracker):
    def op_create_item(self, i):
        self.keys.pop(i["key"], None)
        return super().op_create_item(i)


class LossyWrite(FakeDocuments):
    def op_write(self, i):
        out = super().op_write(i)
        self.docs[i["path"]] = i["content"][:-1]
        return out


class SloppyRevoke(FakeIdentity):
    def op_revoke(self, i):
        out = super().op_revoke(i)
        self.creds[i["credential_id"]]["revoked"] = False
        return out


class SecondKeyForInstance(FakeIdentity):
    def op_issue(self, i):
        self.by_instance.pop(i["instance_id"], None)
        return super().op_issue(i)


class DowngradingAcquire(FakeInstances):
    def op_acquire(self, i):
        out = super().op_acquire(i)
        out["granted"]["network"] = {"mode": "allow-list", "allow": ["*"]}
        return out


class KeepsThinking(FakeSessions):
    def op_export(self, i):
        out = super().op_export(i)
        out["record"]["messages"] = [{"role": s["type"], "text": s["text"]} for s in i["native"]]
        out["dropped_thinking"] = 0
        return out


class ForgetsNothing(FakeMemory):
    def op_forget(self, i):
        return {"key": i["key"], "forgotten": True}


class AcceptsAnyMetric(FakeMetrics):
    def op_observe(self, i):
        self.catalog.add(i["metric"])
        return super().op_observe(i)


class DoubleCounts(FakeMetrics):
    def op_observe(self, i):
        self.seen.clear()
        return super().op_observe(i)


class MutatingRecall(FakeMemory):
    def op_recall(self, i):
        out = super().op_recall(i)
        self.kv.pop(i["key"], None)
        return out


class SilentNoValidation(FakeChannel):
    def call(self, op, inp):
        return getattr(self, "op_" + op.replace("-", "_"))({"channel": "c", "sender": "s", "message_id": "x", "text": "t", **inp})


BROKEN = [
    ("Channel", NonIdempotentSend, "Channel.send: idempotent"),
    ("Channel", UnorderedSubscribe, "Channel.subscribe: ordered"),
    ("Tracker", DuplicatingCreate, "Tracker.create-item: idempotent"),
    ("Documents", LossyWrite, "Documents.write: durable"),
    ("Identity", SloppyRevoke, "Identity.revoke: revocation-effective"),
    ("Identity", SecondKeyForInstance, "Identity.issue: one-key-per-instance"),
    ("Instances", DowngradingAcquire, "Instances.acquire: requirements-honoured"),
    ("Sessions", KeepsThinking, "Sessions.export: thinking-dropped-counted"),
    ("Memory", ForgetsNothing, "Memory.forget: forgotten-not-recalled"),
    ("Metrics", AcceptsAnyMetric, "Metrics.observe: unknown-refused"),
    ("Metrics", DoubleCounts, "Metrics.observe: idempotent"),
    ("Memory", MutatingRecall, "Memory.recall: read-only"),
]


# ---------------------------------------------------------------- acceptance 1: one file per port, seven parts


def test_one_contract_file_per_port():
    assert sorted(p.name for p in CONTRACTS.glob("*.json")) == sorted(f"{p.lower()}.json" for p in PORTS)


@pytest.mark.parametrize("port", PORTS)
def test_contract_names_its_port_and_every_operation(port):
    doc = load(port)
    assert doc["port"] == port
    assert sorted(doc["operations"]) == sorted(OPS[port])


@pytest.mark.parametrize("port", PORTS)
def test_every_operation_has_the_seven_parts(port):
    for name, op in load(port)["operations"].items():
        assert all(part in op for part in PARTS), (port, name)
        assert op["name"] == name


@pytest.mark.parametrize("port", PORTS)
def test_contracts_pass_the_validator(port):
    assert cf.validate_contract(load(port), CATALOG) == []


@pytest.mark.parametrize("port", PORTS)
def test_contracts_declare_every_guarantee_the_harness_tests(port):
    declared = {(port, n, g) for n, op in load(port)["operations"].items() for g in op["guarantees"]}
    tested = {k for k in cf.GUARANTEE_TESTS if k[0] == port}
    assert declared == tested


def test_metric_names_in_contracts_are_catalog_names():
    used = {m for p in PORTS for op in load(p)["operations"].values() for m in op["metrics"]}
    assert used and used <= set(CATALOG)


def test_committed_contracts_hold_no_local_paths():
    text = "".join(f.read_text() for f in CONTRACTS.glob("*.json"))
    for needle in ("claude-501", "/Users/", "~/Fun", "/private/tmp"):
        assert needle not in text


# ---------------------------------------------------------------- owner decision O4 and the identity port


def test_instance_request_carries_isolation_network_trust_and_lifetime_only():
    schema = load("Instances")["operations"]["acquire"]["input"]
    assert sorted(schema["properties"]) == ["isolation", "lifetime_seconds", "network", "trust"]
    assert sorted(schema["required"]) == sorted(schema["properties"])
    assert schema["additionalProperties"] is False


def test_instance_request_cannot_name_an_owner():
    fake = FakeInstances(load("Instances"))
    req = {"isolation": "vm", "network": {"mode": "none"}, "trust": "untrusted", "lifetime_seconds": 60}
    with pytest.raises(PortError) as e:
        fake.call("acquire", {**req, "notify_owner": "me"})
    assert e.value.code == "invalid-input"


def test_instances_contract_notes_the_sandy_macos_gap():
    notes = json.dumps(load("Instances").get("notes", []))
    assert "macOS" in notes and "trusted" in notes


def test_identity_port_is_functional_with_openssh_ca_as_first_implementation():
    doc = load("Identity")
    assert sorted(doc["operations"]) == ["issue", "list", "revoke", "verify"]
    assert "OpenSSH CA" in json.dumps(doc.get("notes", []))
    # key material and backend names stay out of the operation schemas
    for op in doc["operations"].values():
        text = json.dumps([op["input"], op["output"]])
        assert "ssh" not in text.lower() and "key" not in text.lower().replace("key_id", "")


def test_session_export_contract_counts_dropped_thinking():
    assert "dropped_thinking" in load("Sessions")["operations"]["export"]["output"]["properties"]


# ---------------------------------------------------------------- acceptance 2: fakes pass the harness


@pytest.mark.parametrize("port", PORTS)
def test_in_memory_fake_passes_conformance(port):
    contract = load(port)
    assert cf.run_port(contract, FAKES[port](contract), CATALOG) == []


def test_harness_runs_the_tests_it_declares():
    contract = load("Channel")
    ran = []
    original = dict(cf.GUARANTEE_TESTS)
    try:
        for key, fn in original.items():
            cf.GUARANTEE_TESTS[key] = (lambda f, k=key: (lambda *a, **kw: (ran.append(k), f(*a, **kw))[1]))(fn)
        cf.run_port(contract, FakeChannel(contract), CATALOG)
    finally:
        cf.GUARANTEE_TESTS.clear()
        cf.GUARANTEE_TESTS.update(original)
    assert {k for k in ran if k[0] == "Channel"} == {k for k in original if k[0] == "Channel"}


# ---------------------------------------------------------------- acceptance 3 [A]: broken fakes fail the matching test


@pytest.mark.parametrize("port,cls,expected", BROKEN, ids=[b[2] for b in BROKEN])
def test_broken_fake_fails_the_matching_guarantee(port, cls, expected):
    contract = load(port)
    failures = cf.run_port(contract, cls(contract), CATALOG)
    assert any(f.startswith(expected) for f in failures), failures


@pytest.mark.parametrize("port,cls,expected", BROKEN, ids=[b[2] for b in BROKEN])
def test_broken_fake_fails_only_its_own_guarantee_family(port, cls, expected):
    contract = load(port)
    failures = cf.run_port(contract, cls(contract), CATALOG)
    assert failures and all(f.split(": ")[0] == expected.split(": ")[0] for f in failures)


def test_adapter_that_skips_input_validation_is_caught():
    contract = load("Channel")
    failures = cf.run_port(contract, SilentNoValidation(contract), CATALOG)
    assert any("invalid-input" in f for f in failures), failures


def test_adapter_output_that_breaks_the_output_schema_is_caught():
    class BadOutput(FakeChannel):
        def op_list_participants(self, i):
            return {"participants": "alice"}

    contract = load("Channel")
    failures = cf.run_port(contract, BadOutput(contract), CATALOG)
    assert any("Channel.list-participants" in f and "output" in f for f in failures), failures


def test_adapter_that_raises_an_undeclared_error_code_is_caught():
    class Odd(FakeMemory):
        def op_recall(self, i):
            raise PortError("kaboom", "x")

    contract = load("Memory")
    failures = cf.run_port(contract, Odd(contract), CATALOG)
    assert any("kaboom" in f for f in failures), failures


# ---------------------------------------------------------------- acceptance 4 [A]: validator refuses a bad contract


@pytest.mark.parametrize("part", PARTS)
def test_contract_with_a_missing_part_is_refused(part):
    doc = load("Channel")
    del doc["operations"]["send"][part]
    errs = cf.validate_contract(doc, CATALOG)
    assert any("Channel.send" in e and "missing part" in e and part in e for e in errs), errs


def test_contract_missing_an_operation_is_refused():
    doc = load("Channel")
    del doc["operations"]["subscribe"]
    assert any("subscribe" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_with_an_unknown_port_is_refused():
    doc = load("Channel")
    doc["port"] = "Telepathy"
    assert any("unknown port" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_with_a_metric_outside_the_catalog_is_refused():
    doc = load("Channel")
    doc["operations"]["send"]["metrics"] = ["vibes"]
    assert any("vibes" in e and "catalog" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_with_an_untested_guarantee_is_refused():
    doc = load("Channel")
    doc["operations"]["send"]["guarantees"].append("telepathic")
    assert any("telepathic" in e and "no conformance test" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_with_an_open_input_schema_is_refused():
    doc = load("Channel")
    del doc["operations"]["send"]["input"]["additionalProperties"]
    assert any("additionalProperties" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_with_a_requirement_key_outside_the_four_is_refused():
    doc = load("Instances")
    doc["operations"]["acquire"]["requirements"]["owner"] = "me"
    assert any("owner" in e and "requirements" in e for e in cf.validate_contract(doc, CATALOG))


def test_contract_without_invalid_input_in_its_errors_is_refused():
    doc = load("Memory")
    doc["operations"]["recall"]["errors"].remove("invalid-input")
    assert any("invalid-input" in e for e in cf.validate_contract(doc, CATALOG))


def test_validator_never_raises_on_odd_values():
    for bad in (None, 1, [], "x", {}, {"port": 3}, {"port": "Channel", "operations": []},
                {"port": "Channel", "operations": {"send": 1}}):
        assert cf.validate_contract(bad, CATALOG)


# ---------------------------------------------------------------- the schema subset


def test_schema_subset_catches_the_basic_violations():
    s = {"type": "object", "required": ["a"], "additionalProperties": False,
         "properties": {"a": {"type": "integer", "minimum": 1}, "b": {"enum": ["x"]}, "c": {"type": "array", "items": {"type": "string"}}}}
    assert cf.check_schema({"a": 1}, s) == []
    assert cf.check_schema({}, s)
    assert cf.check_schema({"a": 0}, s)
    assert cf.check_schema({"a": True}, s)
    assert cf.check_schema({"a": 1, "z": 1}, s)
    assert cf.check_schema({"a": 1, "b": "y"}, s)
    assert cf.check_schema({"a": 1, "c": [1]}, s)


# ---------------------------------------------------------------- the command line and the import rule


def run_cli(*args):
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "conformance.py"), *args], capture_output=True, text=True)


def test_cli_validates_the_committed_contracts():
    r = run_cli("validate", str(CONTRACTS))
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_refuses_a_contract_with_a_missing_part(tmp_path):
    for f in CONTRACTS.glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    doc = json.loads((tmp_path / "memory.json").read_text())
    del doc["operations"]["recall"]["guarantees"]
    (tmp_path / "memory.json").write_text(json.dumps(doc))
    r = run_cli("validate", str(tmp_path))
    assert r.returncode == 1 and "missing part" in r.stdout + r.stderr


def test_cli_usage_error_is_exit_2():
    assert run_cli().returncode == 2


def test_cli_reads_the_catalog_from_a_file(tmp_path):
    cat = tmp_path / "metrics.json"
    cat.write_text(json.dumps({"only-this": {}}))
    r = run_cli("validate", str(CONTRACTS), "--catalog", str(cat))
    assert r.returncode == 1 and "catalog" in r.stdout + r.stderr


def test_core_imports_the_standard_library_only():
    names = {l.split()[1].split(".")[0] for l in (SKILL / "scripts" / "conformance.py").read_text().splitlines()
             if l.startswith(("import ", "from "))}
    assert names <= set(sys.stdlib_module_names), names
