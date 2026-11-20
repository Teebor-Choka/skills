#!/usr/bin/env python3
"""Operation contracts: contract validator and conformance harness. Standard library only.

A contract file describes one port. Each operation has seven parts: name, input, output,
requirements, guarantees, errors, metrics. An adapter is any object with `call(op, input) -> dict`
that raises `PortError(code, message)` for a declared error.

Every guarantee the harness can test for an operation is mandatory in its contract: an empty or
incomplete `guarantees` list is refused, and `run_port` refuses a refused contract.

Durability: an adapter may define `reopen()`, which drops in-memory state and reloads from storage.
The durable tests call it between write and read. Without it, durability is only checked in-process
(read-your-writes). Every id a test creates carries a per-run nonce, so a persistent adapter can be
tested again.

The harness probes `invalid-input` one violation at a time: an extra key, a missing required key,
a wrong type, an enum violation, a below-minimum value, a bool where a number is required. It also
probes the declared `not-found` and `unknown-metric` errors. Declared errors it cannot trigger
(`channel-unavailable`, `tracker-unavailable`, `backend-unavailable`, `write-refused`, `capacity`,
`unsatisfiable`, `refused-untrusted`, `unsupported-format`, `already-issued` apart from its guarantee
test) are not tested, except that a refused `acquire` may use `unsatisfiable`, `capacity` or
`refused-untrusted`.

    op_conformance.py validate <contracts-dir> [--catalog <metrics.json>]

Exit 0: valid. 1: a contract is refused. 2: usage or load error.
"""
import json
import math
import sys
import uuid
from pathlib import Path

PARTS = ("name", "input", "output", "requirements", "guarantees", "errors", "metrics")
REQUIREMENT_KEYS = ("isolation", "network", "trust", "lifetime")
PORTS = {
    "Channel": ("send", "subscribe", "list-participants"),
    "Tracker": ("create-item", "update-item", "get-item", "search-items", "link-items"),
    "Documents": ("read", "write", "search", "share"),
    "Identity": ("issue", "revoke", "verify", "list"),
    "Instances": ("acquire", "release", "status"),
    "Sessions": ("export",),
    "Memory": ("recall", "remember", "forget"),
    "Metrics": ("observe", "query"),
}
# Names from the first metric catalog (execution plan, Appendix A). Pass the real catalog with --catalog.
CATALOG_NAMES = (
    "escalations", "spec-rework", "acceptance-coverage", "red-for-wrong-reason", "acceptance-rounds",
    "defects-found-in-review", "defects-escaped", "lead-time", "decision-latency", "write-set-collisions",
    "review-rounds", "report-complete", "proposals-accepted", "tests-per-unit", "diff-lines", "green-rounds",
)


class PortError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}")
        self.code = code


# ------------------------------------------------------------------ schema subset

SCHEMA_KEYWORDS = ("type", "properties", "required", "additionalProperties", "items", "enum", "minimum")
SCHEMA_TYPES = ("object", "array", "string", "boolean", "integer", "number")


def _is_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _type_ok(value, t):
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return _is_number(value)
    return False


def check_schema(value, schema, path="$"):
    """Check `value` against the JSON Schema subset the contracts use. Returns a list of errors.

    Keywords: type, properties, required, additionalProperties (false only), items, enum, minimum.
    A float such as 1.0 is refused for `integer`. NaN and Infinity are not numbers. `enum` compares
    type-strictly: True is not 1 and 1.0 is not 1.
    """
    errs = []
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    t = schema.get("type")
    if t is not None and not _type_ok(value, t):
        return [f"{path}: expected {t}"]
    if "enum" in schema and not any(type(value) is type(e) and value == e for e in schema["enum"]):
        errs.append(f"{path}: not one of {schema['enum']}")
    if "minimum" in schema and _is_number(value) and value < schema["minimum"]:
        errs.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}: missing required '{key}'")
        for key, sub in value.items():
            if key in props:
                errs += check_schema(sub, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unexpected property '{key}'")
    if isinstance(value, list) and "items" in schema:
        for n, sub in enumerate(value):
            errs += check_schema(sub, schema["items"], f"{path}[{n}]")
    return errs


def _shape(schema, path):
    """Errors in the shape of a contract schema: unsupported keywords, wrong keyword values."""
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    errs = [f"{path}: unsupported keyword '{k}'" for k in schema if k not in SCHEMA_KEYWORDS]
    t = schema.get("type")
    if "type" in schema and (not isinstance(t, str) or t not in SCHEMA_TYPES):
        errs.append(f"{path}: type must be one of {list(SCHEMA_TYPES)}")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        errs.append(f"{path}: additionalProperties must be false")
    if t == "object" and schema.get("additionalProperties") is not False:
        errs.append(f"{path}: object must set additionalProperties false")
    props = schema.get("properties", {})
    if "properties" in schema and not isinstance(props, dict):
        errs.append(f"{path}: properties must be an object")
        props = {}
    for key, sub in props.items():
        errs += _shape(sub, f"{path}.{key}")
    if "required" in schema:
        req = schema["required"]
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            errs.append(f"{path}: required must be a list of strings")
        else:
            errs += [f"{path}: required '{r}' is not a declared property" for r in req if r not in props]
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        errs.append(f"{path}: enum must be a non-empty list")
    if "minimum" in schema and not _is_number(schema["minimum"]):
        errs.append(f"{path}: minimum must be a finite number")
    if "items" in schema:
        errs += _shape(schema["items"], f"{path}[]")
    return errs


# ------------------------------------------------------------------ guarantee tests
# Each test is fn(c) and raises AssertionError on a violation. `c.call` validates input and output
# against the contract and refuses undeclared error codes. `c.uid(label)` makes a per-run id.


class _Ctx:
    def __init__(self, call, catalog, reopen, nonce):
        self.call, self.catalog, self.reopen, self.nonce = call, catalog, reopen, nonce

    def uid(self, label):
        return f"{label}-{self.nonce}"


def _expect_error(call, code, op, inp):
    try:
        call(op, inp)
    except PortError as e:
        assert e.code == code, f"expected error '{code}', got '{e.code}'"
        return
    raise AssertionError(f"expected error '{code}', call succeeded")


def _msg(channel, mid, sender="alice", text="hi"):
    return {"channel": channel, "message_id": mid, "sender": sender, "text": text}


def _ids(out):
    return [m["message_id"] for m in out["messages"]]


def t_send_idempotent(c):
    ch, m = c.uid("c-idem"), c.uid("m1")
    a = c.call("send", _msg(ch, m))
    assert a["duplicate"] is False, "first send reported duplicate true"
    b = c.call("send", _msg(ch, m))
    assert b["seq"] == a["seq"] and b["duplicate"] is True, f"second send gave {b}, first gave {a}"
    got = _ids(c.call("subscribe", {"channel": ch}))
    assert got == [m], f"message delivered {len(got)} times"


def t_send_durable(c):
    ch, m = c.uid("c-dur"), c.uid("m1")
    c.call("send", _msg(ch, m))
    c.reopen()
    assert _ids(c.call("subscribe", {"channel": ch})) == [m], "sent message not found by subscribe"


def t_subscribe_ordered(c):
    ch = c.uid("c-ord")
    empty = c.call("subscribe", {"channel": ch})
    assert empty["messages"] == [] and empty["cursor"] == 0, "fresh channel is not empty at cursor 0"
    names = [c.uid(n) for n in ("m3", "m1", "m2", "m4", "m5", "m6", "m7", "m8", "m9", "m10", "m11", "m12")]
    seqs = [c.call("send", _msg(ch, n))["seq"] for n in names]
    got = c.call("subscribe", {"channel": ch})
    assert _ids(got) == names, "messages not in send order"
    assert [m["seq"] for m in got["messages"]] == seqs and seqs == sorted(set(seqs)), "seq not strictly increasing"
    rest = c.call("subscribe", {"channel": ch, "after": seqs[0]})
    assert _ids(rest) == names[1:], "cursor did not skip the first message"
    assert rest["cursor"] == seqs[-1], "cursor is not the last seq"
    tail = c.call("subscribe", {"channel": ch, "after": rest["cursor"]})
    assert tail["messages"] == [] and tail["cursor"] == rest["cursor"], "empty result moved the cursor"


def t_subscribe_read_only(c):
    ch = c.uid("c-ro")
    c.call("send", _msg(ch, c.uid("m1")))
    assert c.call("subscribe", {"channel": ch}) == c.call("subscribe", {"channel": ch}), "repeat read differs"


def t_participants_read_only(c):
    ch = c.uid("c-part")
    c.call("send", _msg(ch, c.uid("m1"), sender="alice"))
    c.call("send", _msg(ch, c.uid("m2"), sender="bob"))
    a = c.call("list-participants", {"channel": ch})
    assert a == c.call("list-participants", {"channel": ch}), "repeat read differs"
    assert {"alice", "bob"} <= set(a["participants"]), "senders missing from participants"


def t_create_idempotent(c):
    key, title = c.uid("k-idem"), c.uid("idem-title")
    a = c.call("create-item", {"key": key, "title": title})
    assert a["created"] is True, "first create reported created false"
    b = c.call("create-item", {"key": key, "title": title})
    assert a["item_id"] == b["item_id"] and b["created"] is False, f"second create gave {b}, first gave {a}"
    assert len(c.call("search-items", {"text": title})["items"]) == 1, "duplicate item created"


def t_update_idempotent(c):
    item = c.call("create-item", {"key": c.uid("k-upd"), "title": "t"})["item_id"]
    patch = {"item_id": item, "title": "t2", "state": "closed"}
    a, b = c.call("update-item", patch), c.call("update-item", patch)
    assert a == b, "repeating an update changed the result"
    got = c.call("get-item", {"item_id": item})
    assert got["state"] == "closed" and got["title"] == "t2", "update not applied"


def t_get_read_only(c):
    item = c.call("create-item", {"key": c.uid("k-get"), "title": "t"})["item_id"]
    assert c.call("get-item", {"item_id": item}) == c.call("get-item", {"item_id": item}), "repeat read differs"


def t_search_read_only(c):
    title = c.uid("srch-title")
    c.call("create-item", {"key": c.uid("k-srch"), "title": title})
    a = c.call("search-items", {"text": title})
    assert a == c.call("search-items", {"text": title}), "repeat read differs"
    assert len(a["items"]) == 1, "created item not found"


def t_link_idempotent(c):
    a = c.call("create-item", {"key": c.uid("k-la"), "title": "a"})["item_id"]
    b = c.call("create-item", {"key": c.uid("k-lb"), "title": "b"})["item_id"]
    c.call("link-items", {"from_id": a, "to_id": b})
    c.call("link-items", {"from_id": a, "to_id": b})
    assert c.call("get-item", {"item_id": a})["links"].count(b) == 1, "link recorded more than once"


def t_doc_read_only(c):
    path = f"d/{c.uid('ro')}.md"
    c.call("write", {"path": path, "content": "body"})
    a = c.call("read", {"path": path})
    assert a == c.call("read", {"path": path}) and a["content"] == "body", "repeat read differs"


def t_doc_write_idempotent(c):
    w = {"path": f"d/{c.uid('idem')}.md", "content": "same"}
    assert c.call("write", w) == c.call("write", w), "repeating a write changed the result"
    assert c.call("read", {"path": w["path"]})["content"] == "same", "content differs after repeat"


def t_doc_write_durable(c):
    path = f"d/{c.uid('dur')}.md"
    c.call("write", {"path": path, "content": "kept"})
    c.reopen()
    assert c.call("read", {"path": path})["content"] == "kept", "read did not return what was written"


def t_doc_search_read_only(c):
    path, needle = f"d/{c.uid('s')}.md", c.uid("needle")
    c.call("write", {"path": path, "content": needle})
    a = c.call("search", {"text": needle})
    assert a == c.call("search", {"text": needle}) and path in a["paths"], "search unstable or missing hit"


def t_doc_share_idempotent(c):
    path = f"d/{c.uid('sh')}.md"
    c.call("write", {"path": path, "content": "x"})
    a = c.call("share", {"path": path, "with": "bob"})
    b = c.call("share", {"path": path, "with": "bob"})
    assert a == b and b["shared_with"].count("bob") == 1, "share recorded more than once"


def _issue(c, label, kind="agent", subject="builder"):
    return {"instance_id": c.uid(label), "kind": kind, "subject": subject}


def t_issue_idempotent(c):
    req = _issue(c, "inst-a")
    a, b = c.call("issue", req), c.call("issue", req)
    assert a["credential_id"] == b["credential_id"], "repeat issue gave a new credential"
    mine = [x for x in c.call("list", {})["credentials"] if x["instance_id"] == req["instance_id"]]
    assert len(mine) == 1, f"{len(mine)} credentials listed for one instance"


def t_issue_one_key(c):
    req = _issue(c, "inst-b", subject="one")
    c.call("issue", req)
    _expect_error(c.call, "already-issued", "issue", {**req, "kind": "person", "subject": "two"})


def t_issue_reissue(c):
    req = _issue(c, "inst-r")
    old = c.call("issue", req)["credential_id"]
    c.call("revoke", {"credential_id": old})
    new = c.call("issue", req)["credential_id"]
    assert new != old, "re-issue after revoke returned the revoked credential id"
    assert c.call("verify", {"credential_id": new})["valid"] is True, "new credential is not valid"
    assert c.call("verify", {"credential_id": old})["valid"] is False, "old credential became valid again"


def t_revoke_idempotent(c):
    cid = c.call("issue", _issue(c, "inst-c"))["credential_id"]
    c.call("revoke", {"credential_id": cid})
    c.call("revoke", {"credential_id": cid})
    assert c.call("verify", {"credential_id": cid})["valid"] is False, "credential valid after a repeat revoke"


def t_revoke_effective(c):
    cid = c.call("issue", _issue(c, "inst-d", kind="person"))["credential_id"]
    assert c.call("verify", {"credential_id": cid})["valid"] is True, "fresh credential not valid"
    c.call("revoke", {"credential_id": cid})
    assert c.call("verify", {"credential_id": cid})["valid"] is False, "verify accepts a revoked credential"
    assert cid not in [x["credential_id"] for x in c.call("list", {})["credentials"]], "revoked credential listed by default"
    assert cid in [x["credential_id"] for x in c.call("list", {"include_revoked": True})["credentials"]], "include_revoked hides it"


def t_verify_read_only(c):
    cid = c.call("issue", _issue(c, "inst-e"))["credential_id"]
    assert c.call("verify", {"credential_id": cid}) == c.call("verify", {"credential_id": cid}), "repeat read differs"
    assert c.call("verify", {"credential_id": c.uid("no-such")})["valid"] is False, "unknown credential verified"


def t_list_read_only(c):
    c.call("issue", _issue(c, "inst-f"))
    assert c.call("list", {}) == c.call("list", {}), "repeat read differs"


BASELINE = {"isolation": "process", "network": {"mode": "none"}, "trust": "trusted", "lifetime_seconds": 60}
_REQUESTS = (
    BASELINE,
    {"isolation": "vm", "network": {"mode": "none"}, "trust": "untrusted", "lifetime_seconds": 60},
    {"isolation": "process", "network": {"mode": "allow-list", "allow": ["example.org"]}, "trust": "trusted", "lifetime_seconds": 600},
)
_REFUSALS = ("unsatisfiable", "capacity", "refused-untrusted")


def t_acquire_honoured(c):
    for req in _REQUESTS:
        try:
            got = c.call("acquire", req)
        except PortError as e:
            assert req is not BASELINE, f"baseline request refused with '{e.code}'"
            assert e.code in _REFUSALS, f"refused with '{e.code}'"
            assert e.code != "refused-untrusted" or req["trust"] == "untrusted", "refused trusted work as untrusted"
            continue
        assert got["granted"] == req, f"granted {got['granted']} for request {req}"
        assert c.call("status", {"instance_id": got["instance_id"]})["granted"] == req, "status reports a different grant"
        c.call("release", {"instance_id": got["instance_id"]})


def t_network_consistent(c):
    base = {"isolation": "process", "trust": "trusted", "lifetime_seconds": 5}
    for net in ({"mode": "none", "allow": ["example.org"]}, {"mode": "allow-list"}, {"mode": "allow-list", "allow": []}):
        try:
            got = c.call("acquire", {**base, "network": net})
        except PortError as e:
            assert e.code == "invalid-input", f"refused {net} with '{e.code}'"
            continue
        c.call("release", {"instance_id": got["instance_id"]})
        raise AssertionError(f"accepted inconsistent network {net}")


def t_release_idempotent(c):
    iid = c.call("acquire", BASELINE)["instance_id"]
    c.call("release", {"instance_id": iid})
    c.call("release", {"instance_id": iid})
    assert c.call("status", {"instance_id": iid})["state"] == "released", "instance not released"


def t_status_read_only(c):
    iid = c.call("acquire", BASELINE)["instance_id"]
    assert c.call("status", {"instance_id": iid}) == c.call("status", {"instance_id": iid}), "repeat read differs"
    c.call("release", {"instance_id": iid})


_SLICES = [
    {"type": "user", "text": "q"},
    {"type": "thinking", "text": "hmm"},
    {"type": "tool_use", "text": "t1"},
    {"type": "assistant", "text": "a"},
    {"type": "thinking", "text": "more"},
    {"type": "tool_result", "text": "r"},
]


def t_export_idempotent(c):
    e = {"harness": "claude-code", "native": _SLICES}
    assert c.call("export", e) == c.call("export", e), "repeat export differs"


def t_export_thinking(c):
    got = c.call("export", {"harness": "claude-code", "native": _SLICES})
    assert "thinking" not in [m["role"] for m in got["record"]["messages"]], "thinking block kept in the record"
    assert [m["text"] for m in got["record"]["messages"]] == ["q", "t1", "a", "r"], "other messages changed or reordered"
    assert got["dropped_thinking"] == 2, f"dropped_thinking is {got['dropped_thinking']}, expected 2"


def t_recall_read_only(c):
    k = c.uid("m-ro")
    c.call("remember", {"key": k, "value": "v"})
    a = c.call("recall", {"key": k})
    assert a == c.call("recall", {"key": k}) and a["found"], "recall changed what is stored"


def t_remember_idempotent(c):
    k = c.uid("m-idem")
    c.call("remember", {"key": k, "value": "v"})
    c.call("remember", {"key": k, "value": "v"})
    assert c.call("recall", {"key": k}) == {"found": True, "value": "v"}, "repeat remember changed the value"


def t_remember_durable(c):
    k = c.uid("m-dur")
    c.call("remember", {"key": k, "value": "v1"})
    c.call("remember", {"key": k, "value": "v2"})
    c.reopen()
    assert c.call("recall", {"key": k}).get("value") == "v2", "recall did not return the last stored value"


def t_forget_idempotent(c):
    k = c.uid("m-fi")
    c.call("remember", {"key": k, "value": "v"})
    c.call("forget", {"key": k})
    c.call("forget", {"key": k})
    assert c.call("recall", {"key": k})["found"] is False, "value still found after repeat forget"


def t_forget_effective(c):
    a, b = c.uid("m-fa"), c.uid("m-fb")
    c.call("remember", {"key": a, "value": "1"})
    c.call("remember", {"key": b, "value": "2"})
    assert c.call("forget", {"key": a})["forgotten"] is True, "forget of a stored key reported false"
    assert c.call("recall", {"key": a})["found"] is False, "forgotten key still recalled"
    assert c.call("recall", {"key": b}).get("value") == "2", "forget removed another key"
    assert c.call("forget", {"key": c.uid("m-never")})["forgotten"] is False, "forget of an unknown key reported true"


def _count(c, metric):
    return c.call("query", {"metric": metric})


def t_observe_idempotent(c):
    m = sorted(c.catalog)[0]
    before = _count(c, m)
    obs = {"observation_id": c.uid("o-idem"), "metric": m, "value": 1}
    c.call("observe", obs)
    c.call("observe", obs)
    after = _count(c, m)
    assert after["count"] - before["count"] == 1, f"observation counted {after['count'] - before['count']} times"


def t_observe_durable(c):
    m = sorted(c.catalog)[0]
    before = _count(c, m)
    c.call("observe", {"observation_id": c.uid("o-dur"), "metric": m, "value": 5})
    c.reopen()
    after = _count(c, m)
    assert after["count"] - before["count"] == 1 and after["sum"] - before["sum"] == 5, "query does not show the observation"


def t_observe_unknown(c):
    _expect_error(c.call, "unknown-metric", "observe", {"observation_id": c.uid("o-unk"), "metric": "no-such-metric-xyz", "value": 1})


def t_query_read_only(c):
    m = sorted(c.catalog)[0]
    c.call("observe", {"observation_id": c.uid("o-ro"), "metric": m, "value": 1})
    assert _count(c, m) == _count(c, m), "repeat read differs"


GUARANTEE_TESTS = {
    ("Channel", "send", "idempotent"): t_send_idempotent,
    ("Channel", "send", "durable"): t_send_durable,
    ("Channel", "subscribe", "ordered"): t_subscribe_ordered,
    ("Channel", "subscribe", "read-only"): t_subscribe_read_only,
    ("Channel", "list-participants", "read-only"): t_participants_read_only,
    ("Tracker", "create-item", "idempotent"): t_create_idempotent,
    ("Tracker", "update-item", "idempotent"): t_update_idempotent,
    ("Tracker", "get-item", "read-only"): t_get_read_only,
    ("Tracker", "search-items", "read-only"): t_search_read_only,
    ("Tracker", "link-items", "idempotent"): t_link_idempotent,
    ("Documents", "read", "read-only"): t_doc_read_only,
    ("Documents", "write", "idempotent"): t_doc_write_idempotent,
    ("Documents", "write", "durable"): t_doc_write_durable,
    ("Documents", "search", "read-only"): t_doc_search_read_only,
    ("Documents", "share", "idempotent"): t_doc_share_idempotent,
    ("Identity", "issue", "idempotent"): t_issue_idempotent,
    ("Identity", "issue", "one-key-per-instance"): t_issue_one_key,
    ("Identity", "issue", "reissue-new-credential"): t_issue_reissue,
    ("Identity", "revoke", "idempotent"): t_revoke_idempotent,
    ("Identity", "revoke", "revocation-effective"): t_revoke_effective,
    ("Identity", "verify", "read-only"): t_verify_read_only,
    ("Identity", "list", "read-only"): t_list_read_only,
    ("Instances", "acquire", "requirements-honoured"): t_acquire_honoured,
    ("Instances", "acquire", "network-consistent"): t_network_consistent,
    ("Instances", "release", "idempotent"): t_release_idempotent,
    ("Instances", "status", "read-only"): t_status_read_only,
    ("Sessions", "export", "idempotent"): t_export_idempotent,
    ("Sessions", "export", "thinking-dropped-counted"): t_export_thinking,
    ("Memory", "recall", "read-only"): t_recall_read_only,
    ("Memory", "remember", "idempotent"): t_remember_idempotent,
    ("Memory", "remember", "durable"): t_remember_durable,
    ("Memory", "forget", "idempotent"): t_forget_idempotent,
    ("Memory", "forget", "forgotten-not-recalled"): t_forget_effective,
    ("Metrics", "observe", "idempotent"): t_observe_idempotent,
    ("Metrics", "observe", "durable"): t_observe_durable,
    ("Metrics", "observe", "unknown-refused"): t_observe_unknown,
    ("Metrics", "query", "read-only"): t_query_read_only,
}

# Declared errors the harness can trigger with a fixed input: (port, op, code) -> input.
ERROR_PROBES = {
    ("Tracker", "get-item", "not-found"): {"item_id": "no-such-item"},
    ("Tracker", "update-item", "not-found"): {"item_id": "no-such-item"},
    ("Tracker", "link-items", "not-found"): {"from_id": "no-such-item", "to_id": "no-such-item"},
    ("Documents", "read", "not-found"): {"path": "no/such/doc"},
    ("Documents", "share", "not-found"): {"path": "no/such/doc", "with": "bob"},
    ("Identity", "revoke", "not-found"): {"credential_id": "no-such-credential"},
    ("Instances", "release", "not-found"): {"instance_id": "no-such-instance"},
    ("Instances", "status", "not-found"): {"instance_id": "no-such-instance"},
    ("Metrics", "query", "unknown-metric"): {"metric": "no-such-metric-xyz"},
}


# ------------------------------------------------------------------ validator


def _validate(doc, catalog):
    names = set(CATALOG_NAMES if catalog is None else catalog)
    if not isinstance(doc, dict):
        return ["contract: must be an object"]
    port = doc.get("port")
    if not isinstance(port, str) or port not in PORTS:
        return [f"contract: unknown port {port!r}"]
    ops = doc.get("operations")
    if not isinstance(ops, dict):
        return [f"{port}: operations must be an object"]
    errs = []
    if "notes" in doc and (not isinstance(doc["notes"], list) or not all(isinstance(n, str) for n in doc["notes"])):
        errs.append(f"{port}: notes must be a list of strings")
    errs += [f"{port}: missing operation '{n}'" for n in PORTS[port] if n not in ops]
    errs += [f"{port}: unexpected operation '{n}'" for n in ops if n not in PORTS[port]]
    for name, op in ops.items():
        if name not in PORTS[port]:
            continue
        where = f"{port}.{name}"
        if not isinstance(op, dict):
            errs.append(f"{where}: must be an object")
            continue
        errs += [f"{where}: missing part: {part}" for part in PARTS if part not in op]
        if "name" in op and op["name"] != name:
            errs.append(f"{where}: name is {op['name']!r}")
        if "input" in op:
            errs += _shape(op["input"], f"{where}: input")
            if isinstance(op["input"], dict) and op["input"].get("type") != "object":
                errs.append(f"{where}: input must be an object schema")
        if "output" in op:
            errs += _shape(op["output"], f"{where}: output")
            if isinstance(op["output"], dict) and op["output"].get("type") != "object":
                errs.append(f"{where}: output must be an object schema")
        if "requirements" in op:
            req = op["requirements"]
            if not isinstance(req, dict):
                errs.append(f"{where}: requirements must be an object")
            else:
                errs += [
                    f"{where}: requirements: '{k}' is not one of {list(REQUIREMENT_KEYS)}"
                    for k in req
                    if k not in REQUIREMENT_KEYS
                ]
        if "guarantees" in op:
            guar = op["guarantees"]
            if not isinstance(guar, list) or not all(isinstance(g, str) for g in guar):
                errs.append(f"{where}: guarantees must be a list of strings")
            else:
                errs += [
                    f"{where}: guarantee '{g}' has no conformance test"
                    for g in guar
                    if (port, name, g) not in GUARANTEE_TESTS
                ]
                needed = sorted(g for (p, o, g) in GUARANTEE_TESTS if (p, o) == (port, name))
                errs += [f"{where}: guarantee '{g}' is required" for g in needed if g not in guar]
        if "errors" in op:
            codes = op["errors"]
            if not isinstance(codes, list) or not all(isinstance(x, str) for x in codes):
                errs.append(f"{where}: errors must be a list of strings")
            elif "invalid-input" not in codes:
                errs.append(f"{where}: errors must include 'invalid-input'")
        if "metrics" in op:
            mets = op["metrics"]
            if not isinstance(mets, list) or not all(isinstance(m, str) for m in mets):
                errs.append(f"{where}: metrics must be a list of strings")
            else:
                errs += [f"{where}: metrics: '{m}' is not a name in the catalog" for m in mets if m not in names]
    return errs


def validate_contract(doc, catalog=None):
    """Return the errors that make a port contract unusable. An empty list means valid. Never raises."""
    try:
        return _validate(doc, catalog)
    except Exception as e:  # noqa: BLE001
        return [f"contract: validator error: {type(e).__name__}: {e}"]


# ------------------------------------------------------------------ harness


def _sample(schema):
    """A minimal value that satisfies a validated schema."""
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties", {})
        return {k: _sample(props[k]) for k in schema.get("required", [])}
    if t == "array":
        return []
    if t == "string":
        return "x"
    if t == "boolean":
        return False
    return schema.get("minimum", 1)


def _wrong(schema):
    return "x" if schema.get("type") in ("integer", "number", "boolean") else 5


def _probes(schema):
    """Inputs that each break the schema in exactly one way: (name, input)."""
    base = _sample(schema)
    out = [("extra key", {**base, "__unexpected__": 1})]
    for key in schema.get("required", []):
        out.append((f"missing required ({key})", {k: v for k, v in base.items() if k != key}))
    for key, ps in schema.get("properties", {}).items():
        out.append((f"wrong type ({key})", {**base, key: _wrong(ps)}))
        if "enum" in ps:
            out.append((f"enum violation ({key})", {**base, key: "__bad__"}))
        if "minimum" in ps:
            out.append((f"below minimum ({key})", {**base, key: ps["minimum"] - 1}))
        if ps.get("type") in ("integer", "number"):
            out.append((f"bool for number ({key})", {**base, key: True}))
    return out


def run_port(contract, adapter, catalog=None):
    """Run every declared guarantee test and the generic checks. Returns failure strings, empty on a pass.

    A contract that `validate_contract` refuses is refused here too: each error is one failure.
    """
    cat = list(CATALOG_NAMES if catalog is None else catalog)
    refused = validate_contract(contract, cat)
    if refused:
        return [f"contract: refused: {e}" for e in refused]
    port, ops = contract["port"], contract["operations"]
    failures = []
    reopen = getattr(adapter, "reopen", None) or (lambda: None)

    def call(name, inp):
        assert name in ops, f"operation '{name}' not in the contract"
        bad = check_schema(inp, ops[name]["input"])
        assert not bad, f"harness input for {name}: {bad[0]}"
        try:
            out = adapter.call(name, inp)
        except PortError as e:
            assert e.code in ops[name]["errors"], f"undeclared error code '{e.code}' from {name}"
            raise
        bad = check_schema(out, ops[name]["output"])
        assert not bad, f"{name} output: {bad[0]}"
        return out

    ctx = _Ctx(call, cat, reopen, uuid.uuid4().hex[:8])
    for op, spec in ops.items():
        label = f"{port}.{op}"
        for name, probe in _probes(spec["input"]):
            try:
                adapter.call(op, probe)
                failures.append(f"{label}: invalid-input: {name}: accepted")
            except PortError as e:
                if e.code != "invalid-input":
                    failures.append(f"{label}: invalid-input: {name}: refused with '{e.code}'")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{label}: invalid-input: {name}: raised {type(e).__name__}: {e}")
        for g in spec["guarantees"]:
            try:
                GUARANTEE_TESTS[(port, op, g)](ctx)
            except AssertionError as e:
                failures.append(f"{label}: {g}: {e}")
            except PortError as e:
                failures.append(f"{label}: {g}: unexpected error {e.code}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{label}: {g}: raised {type(e).__name__}: {e}")
        for (p, o, code), inp in ERROR_PROBES.items():
            if (p, o) != (port, op) or code not in spec["errors"]:
                continue
            try:
                _expect_error(call, code, op, inp)
            except AssertionError as e:
                failures.append(f"{label}: error:{code}: {e}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{label}: error:{code}: raised {type(e).__name__}: {e}")
    return failures


# ------------------------------------------------------------------ command line


def load_catalog(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        return list(data)
    return [m["name"] if isinstance(m, dict) else m for m in data]


def main(argv):
    args = list(argv)
    if len(args) < 2 or args[0] != "validate":
        print(__doc__, file=sys.stderr)
        return 2
    directory, catalog = args[1], None
    try:
        if "--catalog" in args:
            catalog = load_catalog(args[args.index("--catalog") + 1])
        if not Path(directory).is_dir():
            raise OSError(f"not a directory: {directory}")
        docs = [(f.name, json.loads(f.read_text())) for f in sorted(Path(directory).glob("*.json"))]
    except (OSError, ValueError, IndexError, KeyError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    errs, seen = [], {}
    for name, doc in docs:
        errs += [f"{name}: {e}" for e in validate_contract(doc, catalog)]
        port = doc.get("port") if isinstance(doc, dict) else None
        if port in PORTS:
            if port in seen:
                errs.append(f"{name}: duplicate contract for port '{port}' (also {seen[port]})")
            seen[port] = name
    errs += [f"{directory}: no contract for port '{p}'" for p in PORTS if p not in seen]
    for e in errs:
        print(e)
    if not errs:
        print(f"ok: {len(docs)} contracts")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
