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

import op_conformance as cf  # noqa: E402
from op_conformance import PortError  # noqa: E402

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
        if key in self.by_instance and not self.creds[self.by_instance[key]]["revoked"]:
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
    check_network = True
    refuse_untrusted = False
    no_allow_list = False
    capacity_only_trusted_process = False

    def __init__(self, contract):
        super().__init__(contract)
        self.boxes = {}

    def op_acquire(self, i):
        net = i["network"]
        if self.check_network and (
            (net["mode"] == "none" and net.get("allow")) or (net["mode"] == "allow-list" and not net.get("allow"))
        ):
            raise PortError("invalid-input", "network mode and allow disagree")
        if self.refuse_untrusted and i["trust"] == "untrusted":
            raise PortError("refused-untrusted", "no enforced boundary on this host")
        if self.no_allow_list and net["mode"] == "allow-list":
            raise PortError("unsatisfiable", "no egress boundary")
        if self.capacity_only_trusted_process and (i["isolation"], i["trust"]) != ("process", "trusted"):
            raise PortError("capacity", "no vm slot")
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


class MacInstances(FakeInstances):
    """The macOS adapter the owner requires: refuses untrusted work and has no allow-list boundary."""

    refuse_untrusted = True
    no_allow_list = True


class CappedInstances(FakeInstances):
    capacity_only_trusted_process = True


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
        if i["metric"] not in self.catalog:
            raise PortError("unknown-metric", i["metric"])
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


class NoStoreSend(FakeChannel):
    def op_send(self, i):
        return {"message_id": i["message_id"], "seq": 1, "duplicate": False}


class ConsumingSubscribe(FakeChannel):
    def op_subscribe(self, i):
        out = super().op_subscribe(i)
        self.log[i["channel"]] = []
        return out


class SortsById(FakeChannel):
    def op_subscribe(self, i):
        out = super().op_subscribe(i)
        out["messages"].sort(key=lambda m: m["message_id"])
        return out


class EmptyCursorZero(FakeChannel):
    def op_subscribe(self, i):
        out = super().op_subscribe(i)
        if not out["messages"]:
            out["cursor"] = 0
        return out


class ForgetfulParticipants(FakeChannel):
    def op_list_participants(self, i):
        out = super().op_list_participants(i)
        self.log[i["channel"]] = []
        return out


class FlippingUpdate(FakeTracker):
    def op_update_item(self, i):
        item = self.items.get(i["item_id"])
        if item and i.get("state") == item["state"]:
            i = {**i, "state": "open" if i["state"] == "closed" else "closed"}
        return super().op_update_item(i)


class IgnoresTitleUpdate(FakeTracker):
    def op_update_item(self, i):
        return super().op_update_item({k: v for k, v in i.items() if k != "title"})


class DoubleLink(FakeTracker):
    def op_link_items(self, i):
        a = self._item(i["from_id"])
        self._item(i["to_id"])
        a["links"].append(i["to_id"])
        return {"linked": True}


class MutatingGet(FakeTracker):
    def op_get_item(self, i):
        out = super().op_get_item(i)
        self.items[i["item_id"]]["title"] += "."
        return out


class MutatingSearch(FakeTracker):
    def op_search_items(self, i):
        out = super().op_search_items(i)
        if self.items:
            self.items.pop(next(iter(self.items)))
        return out


class UnknownItemOk(FakeTracker):
    def op_get_item(self, i):
        if i["item_id"] not in self.items:
            return {"item_id": i["item_id"], "title": "", "body": "", "state": "open", "links": []}
        return super().op_get_item(i)


class ReadDeletes(FakeDocuments):
    def op_read(self, i):
        out = super().op_read(i)
        self.docs.pop(i["path"])
        return out


class SearchWipes(FakeDocuments):
    def op_search(self, i):
        out = super().op_search(i)
        self.docs.clear()
        return out


class DoubleShare(FakeDocuments):
    def op_share(self, i):
        if i["path"] not in self.docs:
            raise PortError("not-found", i["path"])
        who = self.shares.setdefault(i["path"], [])
        who.append(i["with"])
        return {"path": i["path"], "shared_with": list(who)}


class MissingDocOk(FakeDocuments):
    def op_read(self, i):
        return {"path": i["path"], "content": self.docs.get(i["path"], "")}


class CacheOnlyDocuments(FakeDocuments):
    """Writes land in a cache that `reopen` drops: durable only in-process."""

    def __init__(self, contract):
        super().__init__(contract)
        self.disk = {}

    def reopen(self):
        self.docs = dict(self.disk)


class DiskDocuments(FakeDocuments):
    """Persists every write; `reopen` reloads from the persisted copy."""

    def __init__(self, contract):
        super().__init__(contract)
        self.disk, self.reopens = {}, 0

    def op_write(self, i):
        out = super().op_write(i)
        self.disk[i["path"]] = i["content"]
        return out

    def reopen(self):
        self.reopens += 1
        self.docs = dict(self.disk)


class RevokeOnce(FakeIdentity):
    def op_revoke(self, i):
        if i["credential_id"] in self.creds and self.creds[i["credential_id"]]["revoked"]:
            raise PortError("not-found", i["credential_id"])
        return super().op_revoke(i)


class VerifyRevokes(FakeIdentity):
    def op_verify(self, i):
        out = super().op_verify(i)
        if i["credential_id"] in self.creds:
            self.creds[i["credential_id"]]["revoked"] = True
        return out


class ListMutates(FakeIdentity):
    def op_list(self, i):
        out = super().op_list(i)
        for c in self.creds.values():
            c["revoked"] = True
        return out


class ReissueReturnsOld(FakeIdentity):
    def op_issue(self, i):
        cid = self.by_instance.get(i["instance_id"])
        if cid:
            c = self.creds[cid]
            return {k: c[k] for k in ("credential_id", "instance_id", "kind", "subject")}
        return super().op_issue(i)


class ReleaseOnce(FakeInstances):
    def op_release(self, i):
        if i["instance_id"] in self.boxes and self.boxes[i["instance_id"]]["state"] == "released":
            raise PortError("not-found", i["instance_id"])
        return super().op_release(i)


class StatusExpires(FakeInstances):
    def op_status(self, i):
        out = super().op_status(i)
        self.boxes[i["instance_id"]]["state"] = "expired"
        return out


class AllowWithNoneAccepted(FakeInstances):
    check_network = False


class WeakerOnUntrusted(FakeInstances):
    """Honours trusted work, grants a process box for untrusted work and says so."""

    def op_acquire(self, i):
        if i["trust"] == "untrusted":
            i = {**i, "isolation": "process"}
        return super().op_acquire(i)


class WeakerGrantAfterRefusalPath(MacInstances):
    def op_acquire(self, i):
        if i["trust"] == "untrusted":
            out = FakeInstances.op_acquire(self, {**i, "isolation": "process"})
            return out
        return super().op_acquire(i)


class RefusesEverything(FakeInstances):
    def op_acquire(self, i):
        raise PortError("refused-untrusted", "no")


class RefusesWithUndeclaredCode(FakeInstances):
    def op_acquire(self, i):
        raise PortError("nope", "no")


class StatusUnknownOk(FakeInstances):
    def op_status(self, i):
        if i["instance_id"] not in self.boxes:
            return {"instance_id": i["instance_id"], "state": "running", "granted": _GRANT}
        return super().op_status(i)


_GRANT = {"isolation": "process", "network": {"mode": "none"}, "trust": "trusted", "lifetime_seconds": 1}


class BoolIsInt(FakeInstances):
    def call(self, op, inp):
        if inp.get("lifetime_seconds") is True:
            inp = {**inp, "lifetime_seconds": 1}
        return super().call(op, inp)


class NondeterministicExport(FakeSessions):
    n = 0

    def op_export(self, i):
        out = super().op_export(i)
        NondeterministicExport.n += 1
        if out["record"]["messages"]:
            out["record"]["messages"][0]["text"] += f"#{NondeterministicExport.n}"
        return out


class ForgetsAll(FakeMemory):
    def op_forget(self, i):
        out = super().op_forget(i)
        self.kv.clear()
        return out


class RememberAppends(FakeMemory):
    def op_remember(self, i):
        self.kv[i["key"]] = self.kv.get(i["key"], "") + i["value"]
        return {"key": i["key"]}


class FirstWriteWins(FakeMemory):
    def op_remember(self, i):
        self.kv.setdefault(i["key"], i["value"])
        return {"key": i["key"]}


class NoStoreRemember(FakeMemory):
    def op_remember(self, i):
        return {"key": i["key"]}


class ObserveNoSum(FakeMetrics):
    def op_observe(self, i):
        if i["metric"] not in self.catalog:
            raise PortError("unknown-metric", i["metric"])
        self.seen.add(i["observation_id"])
        return {"recorded": True}


class QueryResets(FakeMetrics):
    def op_query(self, i):
        out = super().op_query(i)
        self.sums.pop(i["metric"], None)
        return out


class UnknownQueryOk(FakeMetrics):
    def op_query(self, i):
        return {"metric": i["metric"], "count": 0, "sum": 0}


# (port, broken fake, the guarantee that must fail, other tests that legitimately depend on the broken operation)
BROKEN = [
    ("Channel", NonIdempotentSend, "Channel.send: idempotent", set()),
    ("Channel", NoStoreSend, "Channel.send: durable", {"Channel.subscribe: ordered", "Channel.subscribe: read-only", "Channel.list-participants: read-only", "Channel.send: idempotent"}),
    ("Channel", UnorderedSubscribe, "Channel.subscribe: ordered", set()),
    ("Channel", SortsById, "Channel.subscribe: ordered", set()),
    ("Channel", EmptyCursorZero, "Channel.subscribe: ordered", set()),
    ("Channel", ConsumingSubscribe, "Channel.subscribe: read-only", {"Channel.subscribe: ordered", "Channel.send: idempotent", "Channel.send: durable"}),
    ("Channel", ForgetfulParticipants, "Channel.list-participants: read-only", set()),
    ("Tracker", DuplicatingCreate, "Tracker.create-item: idempotent", set()),
    ("Tracker", FlippingUpdate, "Tracker.update-item: idempotent", set()),
    ("Tracker", IgnoresTitleUpdate, "Tracker.update-item: idempotent", set()),
    ("Tracker", DoubleLink, "Tracker.link-items: idempotent", set()),
    ("Tracker", MutatingGet, "Tracker.get-item: read-only", {"Tracker.update-item: idempotent"}),
    ("Tracker", MutatingSearch, "Tracker.search-items: read-only", {"Tracker.create-item: idempotent"}),
    ("Tracker", UnknownItemOk, "Tracker.get-item: error:not-found", set()),
    ("Documents", LossyWrite, "Documents.write: durable", {"Documents.read: read-only", "Documents.write: idempotent", "Documents.search: read-only"}),
    ("Documents", ReadDeletes, "Documents.read: read-only", {"Documents.write: idempotent", "Documents.write: durable"}),
    ("Documents", SearchWipes, "Documents.search: read-only", set()),
    ("Documents", DoubleShare, "Documents.share: idempotent", set()),
    ("Documents", MissingDocOk, "Documents.read: error:not-found", set()),
    ("Documents", CacheOnlyDocuments, "Documents.write: durable", set()),
    ("Identity", SloppyRevoke, "Identity.revoke: revocation-effective", {"Identity.revoke: idempotent"}),
    ("Identity", SecondKeyForInstance, "Identity.issue: one-key-per-instance", {"Identity.issue: idempotent"}),
    ("Identity", RevokeOnce, "Identity.revoke: idempotent", set()),
    ("Identity", VerifyRevokes, "Identity.verify: read-only", {"Identity.revoke: revocation-effective"}),
    ("Identity", ListMutates, "Identity.list: read-only", {"Identity.revoke: revocation-effective"}),
    ("Identity", ReissueReturnsOld, "Identity.issue: reissue-new-credential", set()),
    ("Instances", DowngradingAcquire, "Instances.acquire: requirements-honoured", set()),
    ("Instances", WeakerOnUntrusted, "Instances.acquire: requirements-honoured", set()),
    ("Instances", WeakerGrantAfterRefusalPath, "Instances.acquire: requirements-honoured", set()),
    ("Instances", RefusesEverything, "Instances.acquire: requirements-honoured", {"Instances.release: idempotent", "Instances.status: read-only"}),
    ("Instances", RefusesWithUndeclaredCode, "Instances.acquire: requirements-honoured", {"Instances.release: idempotent", "Instances.status: read-only"}),
    ("Instances", AllowWithNoneAccepted, "Instances.acquire: network-consistent", set()),
    ("Instances", ReleaseOnce, "Instances.release: idempotent", set()),
    ("Instances", StatusExpires, "Instances.status: read-only", {"Instances.release: idempotent"}),
    ("Instances", StatusUnknownOk, "Instances.status: error:not-found", set()),
    ("Sessions", KeepsThinking, "Sessions.export: thinking-dropped-counted", set()),
    ("Sessions", NondeterministicExport, "Sessions.export: idempotent", {"Sessions.export: thinking-dropped-counted"}),
    ("Memory", ForgetsNothing, "Memory.forget: forgotten-not-recalled", {"Memory.forget: idempotent"}),
    ("Memory", ForgetsAll, "Memory.forget: forgotten-not-recalled", set()),
    ("Memory", MutatingRecall, "Memory.recall: read-only", set()),
    ("Memory", RememberAppends, "Memory.remember: idempotent", {"Memory.remember: durable", "Memory.recall: read-only"}),
    ("Memory", FirstWriteWins, "Memory.remember: durable", set()),
    ("Memory", NoStoreRemember, "Memory.remember: durable", {"Memory.remember: idempotent", "Memory.recall: read-only", "Memory.forget: idempotent", "Memory.forget: forgotten-not-recalled"}),
    ("Metrics", AcceptsAnyMetric, "Metrics.observe: unknown-refused", set()),
    ("Metrics", DoubleCounts, "Metrics.observe: idempotent", set()),
    ("Metrics", ObserveNoSum, "Metrics.observe: durable", {"Metrics.observe: idempotent"}),
    ("Metrics", QueryResets, "Metrics.query: read-only", {"Metrics.observe: idempotent", "Metrics.observe: durable"}),
    ("Metrics", UnknownQueryOk, "Metrics.query: error:unknown-metric", set()),
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


def test_every_contract_says_metrics_emission_is_not_tested():
    for port in PORTS:
        assert "metrics emission is not tested" in json.dumps(load(port).get("notes", [])), port


def test_declared_metrics_are_catalog_names_and_a_catalog_name_is_accepted():
    for port in PORTS:
        for op in load(port)["operations"].values():
            assert set(op["metrics"]) <= set(CATALOG)
    doc = load("Channel")
    doc["operations"]["send"]["metrics"] = ["escalations"]
    assert cf.validate_contract(doc, CATALOG) == []


def test_catalog_file_formats_match_the_u1_fixture():
    fixture = HERE / "fixtures" / "validate_org" / "catalog.json"
    if not fixture.exists():
        pytest.skip("U1 catalog fixture is not on this branch yet")
    names = cf.load_catalog(str(fixture))
    assert set(names) == set(CATALOG)
    r = run_cli("validate", str(CONTRACTS), "--catalog", str(fixture))
    assert r.returncode == 0, r.stdout


def test_catalog_loader_accepts_a_name_list_and_a_name_map(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(["x", {"name": "y"}]))
    (tmp_path / "b.json").write_text(json.dumps({"x": {}, "y": {}}))
    assert cf.load_catalog(str(tmp_path / "a.json")) == ["x", "y"]
    assert cf.load_catalog(str(tmp_path / "b.json")) == ["x", "y"]


def test_committed_contracts_hold_no_local_paths():
    text = "".join(f.read_text() for f in CONTRACTS.glob("*.json"))
    for needle in ("claude" + "-501", "/Us" + "ers/", "~/" + "Fun", "/private" + "/tmp"):
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


def labels(failures):
    return {": ".join(f.split(": ", 2)[:2]) for f in failures}


@pytest.mark.parametrize("port,cls,expected,_dep", BROKEN, ids=[f"{b[1].__name__}" for b in BROKEN])
def test_broken_fake_fails_the_matching_guarantee(port, cls, expected, _dep):
    contract = load(port)
    failures = cf.run_port(contract, cls(contract), CATALOG)
    assert any(f.startswith(expected) for f in failures), failures


@pytest.mark.parametrize("port,cls,expected,dependents", BROKEN, ids=[f"{b[1].__name__}" for b in BROKEN])
def test_broken_fake_leaves_unrelated_guarantees_passing(port, cls, expected, dependents):
    contract = load(port)
    failed = labels(cf.run_port(contract, cls(contract), CATALOG))
    assert failed - {expected} <= dependents, sorted(failed - {expected} - dependents)


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
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "op_conformance.py"), *args], capture_output=True, text=True)


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
    names = {l.split()[1].split(".")[0] for l in (SKILL / "scripts" / "op_conformance.py").read_text().splitlines()
             if l.startswith(("import ", "from "))}
    assert names <= set(sys.stdlib_module_names), names


# ================================================================ review 1

# ---- B1: the guarantees the harness tests are mandatory, and run_port refuses a broken contract


def test_empty_guarantee_lists_are_refused_with_a_location():
    doc = load("Channel")
    for op in doc["operations"].values():
        op["guarantees"] = []
    errs = cf.validate_contract(doc, CATALOG)
    assert any("Channel.send" in e and "idempotent" in e and "required" in e for e in errs), errs
    assert any("Channel.subscribe" in e and "ordered" in e for e in errs), errs


def test_an_incomplete_guarantee_list_is_refused():
    doc = load("Identity")
    doc["operations"]["revoke"]["guarantees"].remove("revocation-effective")
    errs = cf.validate_contract(doc, CATALOG)
    assert any("Identity.revoke" in e and "revocation-effective" in e and "required" in e for e in errs), errs


def test_run_port_refuses_a_contract_that_would_test_nothing():
    good = load("Channel")
    bad = load("Channel")
    for op in bad["operations"].values():
        op["guarantees"] = []
    failures = cf.run_port(bad, FakeChannel(good), CATALOG)
    assert failures and all("contract" in f and "refused" in f for f in failures), failures


def test_run_port_refuses_instead_of_raising_on_a_malformed_contract():
    good = load("Channel")
    for bad in (None, {}, {"port": "Channel"}, {"port": "Channel", "operations": {"send": 1}}):
        failures = cf.run_port(bad, FakeChannel(good), CATALOG)
        assert failures and "refused" in failures[0]


# ---- B2: malformed schemas are refusals, never exceptions


def _with(doc_port, mutate):
    doc = load(doc_port)
    mutate(doc)
    return doc


MALFORMED = {
    "required is a number": lambda d: d["operations"]["send"]["input"].update(required=5),
    "required holds a list": lambda d: d["operations"]["send"]["input"].update(required=[["x"]]),
    "required names no property": lambda d: d["operations"]["send"]["input"].update(required=["ghost"]),
    "properties is a number": lambda d: d["operations"]["send"]["input"].update(properties=5),
    "property schema is a number": lambda d: d["operations"]["send"]["input"]["properties"].update(channel=5),
    "enum is a number": lambda d: d["operations"]["send"]["input"]["properties"]["channel"].update(enum=5),
    "enum is empty": lambda d: d["operations"]["send"]["input"]["properties"]["channel"].update(enum=[]),
    "minimum is a string": lambda d: d["operations"]["subscribe"]["input"]["properties"]["after"].update(minimum="a"),
    "minimum is nan": lambda d: d["operations"]["subscribe"]["input"]["properties"]["after"].update(minimum=float("nan")),
    "minimum is a bool": lambda d: d["operations"]["subscribe"]["input"]["properties"]["after"].update(minimum=True),
    "type is unknown": lambda d: d["operations"]["send"]["input"]["properties"]["channel"].update(type="text"),
    "items is a number": lambda d: d["operations"]["list-participants"]["output"]["properties"]["participants"].update(items=5),
    "output object is open": lambda d: d["operations"]["send"]["output"].pop("additionalProperties"),
    "nested object is open": lambda d: d["operations"]["subscribe"]["output"]["properties"]["messages"]["items"].pop("additionalProperties"),
    "notes is a string": lambda d: d.update(notes="x"),
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_malformed_schema_is_refused_not_raised(name):
    doc = _with("Channel", MALFORMED[name])
    errs = cf.validate_contract(doc, CATALOG)
    assert errs and all(isinstance(e, str) for e in errs), name
    assert any("Channel" in e for e in errs), errs


JUNK = [5, None, "x", [["x"]], {"a": 1}, 1.5, True, [], {}]


def _paths(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _paths(v, prefix + (k,))
    elif isinstance(node, list):
        for n, v in enumerate(node):
            yield from _paths(v, prefix + (n,))


def _set(doc, path, value):
    cur = doc
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value


@pytest.mark.parametrize("port", ["Channel", "Instances", "Sessions"])
def test_validator_and_harness_never_raise_on_any_nested_junk(port):
    base = load(port)
    good = load(port)
    n = 0
    for path in list(_paths(base)):
        if not path:
            continue
        for junk in JUNK:
            doc = copy.deepcopy(base)
            _set(doc, path, copy.deepcopy(junk))
            errs = cf.validate_contract(doc, CATALOG)
            assert isinstance(errs, list), (path, junk)
            res = cf.run_port(doc, FAKES[port](good), CATALOG)
            assert isinstance(res, list), (path, junk)
            n += 1
    assert n > 500


def test_cli_exits_2_for_a_missing_directory(tmp_path):
    r = run_cli("validate", str(tmp_path / "nope"))
    assert r.returncode == 2


def test_cli_prints_no_traceback_for_a_malformed_schema(tmp_path):
    for f in CONTRACTS.glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    doc = json.loads((tmp_path / "channel.json").read_text())
    doc["operations"]["send"]["input"]["required"] = 5
    (tmp_path / "channel.json").write_text(json.dumps(doc))
    r = run_cli("validate", str(tmp_path))
    assert r.returncode == 1 and "Traceback" not in r.stderr and "channel.json" in r.stdout


def test_cli_refuses_two_files_for_one_port(tmp_path):
    for f in CONTRACTS.glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    (tmp_path / "channel-copy.json").write_text((CONTRACTS / "channel.json").read_text())
    r = run_cli("validate", str(tmp_path))
    assert r.returncode == 1 and "duplicate" in r.stdout


# ---- B3: refusal paths of Instances.acquire


def test_macos_style_adapter_that_refuses_untrusted_work_passes():
    c = load("Instances")
    assert cf.run_port(c, MacInstances(c), CATALOG) == []


def test_adapter_at_capacity_for_vms_passes():
    c = load("Instances")
    assert cf.run_port(c, CappedInstances(c), CATALOG) == []


def test_instances_declares_the_refusal_errors():
    errs = load("Instances")["operations"]["acquire"]["errors"]
    assert {"unsatisfiable", "capacity", "refused-untrusted"} <= set(errs)


def test_network_mode_and_allow_must_agree():
    c = load("Instances")
    f = FakeInstances(c)
    base = {"isolation": "process", "trust": "trusted", "lifetime_seconds": 5}
    for net in ({"mode": "none", "allow": ["example.org"]}, {"mode": "allow-list"}, {"mode": "allow-list", "allow": []}):
        with pytest.raises(PortError) as e:
            f.call("acquire", {**base, "network": net})
        assert e.value.code == "invalid-input"
    notes = json.dumps(c.get("notes", []))
    assert "allow" in notes and "mode" in notes


# ---- S1: reopen hook for durability


def test_durable_tests_call_reopen_when_the_adapter_has_it():
    c = load("Documents")
    d = DiskDocuments(c)
    assert cf.run_port(c, d, CATALOG) == []
    assert d.reopens >= 1


def test_the_harness_docstring_says_durability_is_in_process_without_reopen():
    assert "reopen" in cf.__doc__ and "in-process" in cf.__doc__


# ---- S2: ids are unique per run, so a persistent adapter can be tested again


@pytest.mark.parametrize("port", PORTS)
def test_the_harness_is_repeatable_against_one_adapter(port):
    contract = load(port)
    adapter = FAKES[port](contract)
    assert cf.run_port(contract, adapter, CATALOG) == []
    assert cf.run_port(contract, adapter, CATALOG) == []


# ---- S3 and N3: stronger assertions


def test_ordering_is_checked_with_twelve_messages_sent_out_of_name_order():
    c = load("Channel")
    sent = {}

    class Spy(FakeChannel):
        def op_send(self, i):
            sent.setdefault(i["channel"], []).append(i["message_id"])
            return super().op_send(i)

    cf.run_port(c, Spy(c), CATALOG)
    longest = max(sent.values(), key=len)
    assert len(longest) >= 12
    assert [m.split("-")[0] for m in longest[:3]] == ["m3", "m1", "m2"]


def test_first_send_must_report_duplicate_false():
    c = load("Channel")

    class AlwaysDuplicate(FakeChannel):
        def op_send(self, i):
            out = super().op_send(i)
            out["duplicate"] = True
            return out

    assert any(f.startswith("Channel.send: idempotent") for f in cf.run_port(c, AlwaysDuplicate(c), CATALOG))


def test_first_create_must_report_created_true():
    c = load("Tracker")

    class NeverCreated(FakeTracker):
        def op_create_item(self, i):
            out = super().op_create_item(i)
            out["created"] = False
            return out

    assert any(f.startswith("Tracker.create-item: idempotent") for f in cf.run_port(c, NeverCreated(c), CATALOG))


# ---- S4: invalid-input is probed one violation at a time


class AcceptsExtraKeys(FakeChannel):
    def call(self, op, inp):
        schema = self.contract["operations"][op]["input"]
        known = {k: v for k, v in inp.items() if k in schema["properties"]}
        if cf.check_schema(known, schema):
            raise PortError("invalid-input", op)
        return getattr(self, "op_" + op.replace("-", "_"))(known)


class AcceptsWrongType(FakeChannel):
    def call(self, op, inp):
        if isinstance(inp.get("text"), int):
            inp = {**inp, "text": str(inp["text"])}
        return super().call(op, inp)


class IgnoresMinimum(FakeChannel):
    def call(self, op, inp):
        if inp.get("after", 0) < 0:
            inp = {**inp, "after": 0}
        return super().call(op, inp)


class IgnoresEnum(FakeTracker):
    def call(self, op, inp):
        if inp.get("state") == "__bad__":
            inp = {**inp, "state": "open"}
        return super().call(op, inp)


@pytest.mark.parametrize(
    "port,cls,word",
    [
        ("Channel", AcceptsExtraKeys, "extra"),
        ("Channel", AcceptsWrongType, "type"),
        ("Channel", IgnoresMinimum, "minimum"),
        ("Tracker", IgnoresEnum, "enum"),
        ("Instances", BoolIsInt, "bool"),
    ],
)
def test_each_invalid_input_probe_catches_its_own_violation(port, cls, word):
    c = load(port)
    failures = cf.run_port(c, cls(c), CATALOG)
    assert any("invalid-input" in f and word in f for f in failures), failures


# ---- S5: the schema subset is closed

UNSUPPORTED = {
    "anyOf": [{"type": "string"}], "oneOf": [{"type": "string"}], "allOf": [{"type": "string"}],
    "$ref": "#/x", "pattern": "^a", "format": "uri", "maximum": 3, "exclusiveMinimum": 0,
    "minLength": 1, "minItems": 1, "const": "a", "not": {"type": "string"}, "uniqueItems": True,
}


@pytest.mark.parametrize("keyword", list(UNSUPPORTED))
def test_unsupported_schema_keywords_are_refused_with_a_location(keyword):
    doc = load("Channel")
    doc["operations"]["send"]["input"]["properties"]["text"][keyword] = UNSUPPORTED[keyword]
    errs = cf.validate_contract(doc, CATALOG)
    assert any("Channel.send" in e and keyword in e and "unsupported" in e for e in errs), errs


@pytest.mark.parametrize("value", [True, {"type": "string"}, None])
def test_a_non_false_additional_properties_is_refused(value):
    doc = load("Channel")
    doc["operations"]["send"]["output"]["additionalProperties"] = value
    assert any("additionalProperties" in e for e in cf.validate_contract(doc, CATALOG))


def test_nan_and_infinity_are_not_numbers():
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert cf.check_schema(bad, {"type": "number"})


def test_enum_compares_type_strictly():
    assert cf.check_schema(True, {"enum": [1]})
    assert cf.check_schema(1.0, {"enum": [1]})
    assert cf.check_schema(1, {"enum": [1]}) == []
    assert cf.check_schema(0, {"enum": [False]})


def test_a_float_is_refused_for_integer_and_the_docstring_says_so():
    assert cf.check_schema(1.0, {"type": "integer"})
    assert "float" in cf.check_schema.__doc__


# ---- S6 and S7: notes, identity re-issue

def test_identity_notes_state_the_ttl_gap_and_the_reissue_rule():
    notes = json.dumps(load("Identity")["notes"])
    assert "validity window" in notes and "TTL" in notes
    assert "re-issue" in notes and "new credential id" in notes


def test_identity_reissue_after_revoke_gives_a_new_valid_credential():
    c = load("Identity")
    f = FakeIdentity(c)
    req = {"instance_id": "i1", "kind": "agent", "subject": "s"}
    old = f.call("issue", req)["credential_id"]
    f.call("revoke", {"credential_id": old})
    new = f.call("issue", req)["credential_id"]
    assert new != old
    assert f.call("verify", {"credential_id": new})["valid"] is True
    assert f.call("verify", {"credential_id": old})["valid"] is False


def test_notes_may_name_backends_but_schemas_may_not():
    for port in PORTS:
        text = json.dumps([[o["input"], o["output"]] for o in load(port)["operations"].values()]).lower()
        for word in ("openssh", "sandy", "github", "openbao", "vfkit"):
            assert word not in text, (port, word)


# ---- nits


def test_session_slices_cover_tool_use_and_tool_result_and_say_the_other_harnesses_are_unverified():
    doc = load("Sessions")
    slice_type = doc["operations"]["export"]["input"]["properties"]["native"]["items"]["properties"]["type"]
    assert {"user", "assistant", "thinking", "tool_use", "tool_result"} == set(slice_type["enum"])
    assert "unverified" in json.dumps(doc["notes"])


def test_forget_leaves_other_keys_alone():
    c = load("Memory")
    f = FakeMemory(c)
    f.call("remember", {"key": "a", "value": "1"})
    f.call("remember", {"key": "b", "value": "2"})
    f.call("forget", {"key": "a"})
    assert f.call("recall", {"key": "b"})["value"] == "2"
