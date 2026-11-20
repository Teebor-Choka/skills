#!/usr/bin/env python3
"""Operation contracts: contract validator and conformance harness. Standard library only.

A contract file describes one port. Each operation has seven parts: name, input, output,
requirements, guarantees, errors, metrics. An adapter is any object with `call(op, input) -> dict`
that raises `PortError(code, message)` for a declared error.

    op_conformance.py validate <contracts-dir> [--catalog <metrics.json>]

Exit 0: valid. 1: a contract is refused. 2: usage or load error.
"""
import json
import sys
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
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def check_schema(value, schema, path="$"):
    """Check `value` against the JSON Schema subset the contracts use. Returns a list of errors."""
    errs = []
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    t = schema.get("type")
    if t is not None and not _type_ok(value, t):
        return [f"{path}: expected {t}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: not one of {schema['enum']}")
    if "minimum" in schema and _type_ok(value, "number") and value < schema["minimum"]:
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


# ------------------------------------------------------------------ guarantee tests
# Each test is fn(call, catalog) and raises AssertionError on a violation. `call` validates
# input and output against the contract and refuses undeclared error codes.


def _expect_error(call, code, op, inp):
    try:
        call(op, inp)
    except PortError as e:
        assert e.code == code, f"expected error '{code}', got '{e.code}'"
        return
    raise AssertionError(f"expected error '{code}', call succeeded")


def _msg(channel, mid, sender="alice", text="hi"):
    return {"channel": channel, "message_id": mid, "sender": sender, "text": text}


def t_send_idempotent(call, cat):
    a = call("send", _msg("c-idem", "m1"))
    b = call("send", _msg("c-idem", "m1"))
    assert b["seq"] == a["seq"] and b["duplicate"] is True, f"second send gave {b}, first gave {a}"
    ids = [m["message_id"] for m in call("subscribe", {"channel": "c-idem"})["messages"]]
    assert ids == ["m1"], f"message delivered {len(ids)} times"


def t_send_durable(call, cat):
    call("send", _msg("c-dur", "m1"))
    ids = [m["message_id"] for m in call("subscribe", {"channel": "c-dur"})["messages"]]
    assert ids == ["m1"], "sent message not found by subscribe"


def t_subscribe_ordered(call, cat):
    seqs = [call("send", _msg("c-ord", f"m{n}"))["seq"] for n in (1, 2, 3)]
    got = call("subscribe", {"channel": "c-ord"})
    assert [m["message_id"] for m in got["messages"]] == ["m1", "m2", "m3"], "messages not in send order"
    assert [m["seq"] for m in got["messages"]] == sorted(set(seqs)), "seq not strictly increasing"
    rest = call("subscribe", {"channel": "c-ord", "after": seqs[0]})
    assert [m["message_id"] for m in rest["messages"]] == ["m2", "m3"], "cursor did not skip the first message"
    assert rest["cursor"] == seqs[2], "cursor is not the last seq"


def t_subscribe_read_only(call, cat):
    call("send", _msg("c-ro", "m1"))
    assert call("subscribe", {"channel": "c-ro"}) == call("subscribe", {"channel": "c-ro"}), "repeat read differs"


def t_participants_read_only(call, cat):
    call("send", _msg("c-part", "m1", sender="alice"))
    call("send", _msg("c-part", "m2", sender="bob"))
    a = call("list-participants", {"channel": "c-part"})
    assert a == call("list-participants", {"channel": "c-part"}), "repeat read differs"
    assert {"alice", "bob"} <= set(a["participants"]), "senders missing from participants"


def t_create_idempotent(call, cat):
    a = call("create-item", {"key": "k-idem", "title": "idem-title"})
    b = call("create-item", {"key": "k-idem", "title": "idem-title"})
    assert a["item_id"] == b["item_id"] and b["created"] is False, f"second create gave {b}, first gave {a}"
    assert len(call("search-items", {"text": "idem-title"})["items"]) == 1, "duplicate item created"


def t_update_idempotent(call, cat):
    item = call("create-item", {"key": "k-upd", "title": "t"})["item_id"]
    patch = {"item_id": item, "title": "t2", "state": "closed"}
    a, b = call("update-item", patch), call("update-item", patch)
    assert a == b, "repeating an update changed the result"
    assert call("get-item", {"item_id": item})["state"] == "closed", "update not applied"


def t_get_read_only(call, cat):
    item = call("create-item", {"key": "k-get", "title": "t"})["item_id"]
    assert call("get-item", {"item_id": item}) == call("get-item", {"item_id": item}), "repeat read differs"


def t_search_read_only(call, cat):
    call("create-item", {"key": "k-srch", "title": "srch-title"})
    a = call("search-items", {"text": "srch-title"})
    assert a == call("search-items", {"text": "srch-title"}), "repeat read differs"
    assert len(a["items"]) == 1, "created item not found"


def t_link_idempotent(call, cat):
    a = call("create-item", {"key": "k-la", "title": "a"})["item_id"]
    b = call("create-item", {"key": "k-lb", "title": "b"})["item_id"]
    call("link-items", {"from_id": a, "to_id": b})
    call("link-items", {"from_id": a, "to_id": b})
    assert call("get-item", {"item_id": a})["links"].count(b) == 1, "link recorded more than once"


def t_doc_read_only(call, cat):
    call("write", {"path": "d/ro.md", "content": "body"})
    a = call("read", {"path": "d/ro.md"})
    assert a == call("read", {"path": "d/ro.md"}) and a["content"] == "body", "repeat read differs"


def t_doc_write_idempotent(call, cat):
    w = {"path": "d/idem.md", "content": "same"}
    assert call("write", w) == call("write", w), "repeating a write changed the result"
    assert call("read", {"path": "d/idem.md"})["content"] == "same", "content differs after repeat"


def t_doc_write_durable(call, cat):
    call("write", {"path": "d/dur.md", "content": "kept"})
    assert call("read", {"path": "d/dur.md"})["content"] == "kept", "read did not return what was written"


def t_doc_search_read_only(call, cat):
    call("write", {"path": "d/s.md", "content": "needle-xyz"})
    a = call("search", {"text": "needle-xyz"})
    assert a == call("search", {"text": "needle-xyz"}) and "d/s.md" in a["paths"], "search unstable or missing hit"


def t_doc_share_idempotent(call, cat):
    call("write", {"path": "d/sh.md", "content": "x"})
    a = call("share", {"path": "d/sh.md", "with": "bob"})
    b = call("share", {"path": "d/sh.md", "with": "bob"})
    assert a == b and b["shared_with"].count("bob") == 1, "share recorded more than once"


_ISSUE = {"instance_id": "inst-a", "kind": "agent", "subject": "builder"}


def t_issue_idempotent(call, cat):
    a, b = call("issue", _ISSUE), call("issue", _ISSUE)
    assert a["credential_id"] == b["credential_id"], "repeat issue gave a new credential"
    mine = [c for c in call("list", {})["credentials"] if c["instance_id"] == "inst-a"]
    assert len(mine) == 1, f"{len(mine)} credentials listed for one instance"


def t_issue_one_key(call, cat):
    call("issue", {"instance_id": "inst-b", "kind": "agent", "subject": "one"})
    _expect_error(call, "already-issued", "issue", {"instance_id": "inst-b", "kind": "person", "subject": "two"})


def t_revoke_idempotent(call, cat):
    cid = call("issue", {"instance_id": "inst-c", "kind": "agent", "subject": "c"})["credential_id"]
    call("revoke", {"credential_id": cid})
    call("revoke", {"credential_id": cid})
    assert call("verify", {"credential_id": cid})["valid"] is False, "credential valid after a repeat revoke"


def t_revoke_effective(call, cat):
    cid = call("issue", {"instance_id": "inst-d", "kind": "person", "subject": "d"})["credential_id"]
    assert call("verify", {"credential_id": cid})["valid"] is True, "fresh credential not valid"
    call("revoke", {"credential_id": cid})
    assert call("verify", {"credential_id": cid})["valid"] is False, "verify accepts a revoked credential"
    assert cid not in [c["credential_id"] for c in call("list", {})["credentials"]], "revoked credential listed by default"
    assert cid in [c["credential_id"] for c in call("list", {"include_revoked": True})["credentials"]], "include_revoked hides it"


def t_verify_read_only(call, cat):
    cid = call("issue", {"instance_id": "inst-e", "kind": "agent", "subject": "e"})["credential_id"]
    assert call("verify", {"credential_id": cid}) == call("verify", {"credential_id": cid}), "repeat read differs"
    assert call("verify", {"credential_id": "no-such"})["valid"] is False, "unknown credential verified"


def t_list_read_only(call, cat):
    call("issue", {"instance_id": "inst-f", "kind": "agent", "subject": "f"})
    assert call("list", {}) == call("list", {}), "repeat read differs"


_REQUESTS = (
    {"isolation": "vm", "network": {"mode": "none"}, "trust": "untrusted", "lifetime_seconds": 60},
    {"isolation": "process", "network": {"mode": "allow-list", "allow": ["example.org"]}, "trust": "trusted", "lifetime_seconds": 600},
)


def t_acquire_honoured(call, cat):
    for req in _REQUESTS:
        got = call("acquire", req)
        assert got["granted"] == req, f"granted {got['granted']} for request {req}"
        assert call("status", {"instance_id": got["instance_id"]})["granted"] == req, "status reports a different grant"


def t_release_idempotent(call, cat):
    iid = call("acquire", _REQUESTS[0])["instance_id"]
    call("release", {"instance_id": iid})
    call("release", {"instance_id": iid})
    assert call("status", {"instance_id": iid})["state"] == "released", "instance not released"


def t_status_read_only(call, cat):
    iid = call("acquire", _REQUESTS[0])["instance_id"]
    assert call("status", {"instance_id": iid}) == call("status", {"instance_id": iid}), "repeat read differs"


_SLICES = [{"type": "user", "text": "q"}, {"type": "thinking", "text": "hmm"},
           {"type": "assistant", "text": "a"}, {"type": "thinking", "text": "more"}]


def t_export_idempotent(call, cat):
    e = {"harness": "claude-code", "native": _SLICES}
    assert call("export", e) == call("export", e), "repeat export differs"


def t_export_thinking(call, cat):
    got = call("export", {"harness": "claude-code", "native": _SLICES})
    assert "thinking" not in [m["role"] for m in got["record"]["messages"]], "thinking block kept in the record"
    assert [m["text"] for m in got["record"]["messages"]] == ["q", "a"], "other messages changed or reordered"
    assert got["dropped_thinking"] == 2, f"dropped_thinking is {got['dropped_thinking']}, expected 2"


def t_recall_read_only(call, cat):
    call("remember", {"key": "m-ro", "value": "v"})
    a = call("recall", {"key": "m-ro"})
    assert a == call("recall", {"key": "m-ro"}) and a["found"], "recall changed what is stored"


def t_remember_idempotent(call, cat):
    call("remember", {"key": "m-idem", "value": "v"})
    call("remember", {"key": "m-idem", "value": "v"})
    assert call("recall", {"key": "m-idem"}) == {"found": True, "value": "v"}, "repeat remember changed the value"


def t_remember_durable(call, cat):
    call("remember", {"key": "m-dur", "value": "kept"})
    assert call("recall", {"key": "m-dur"}).get("value") == "kept", "recall did not return what was stored"


def t_forget_idempotent(call, cat):
    call("remember", {"key": "m-fi", "value": "v"})
    call("forget", {"key": "m-fi"})
    call("forget", {"key": "m-fi"})
    assert call("recall", {"key": "m-fi"})["found"] is False, "value still found after repeat forget"


def t_forget_effective(call, cat):
    call("remember", {"key": "m-fe", "value": "v"})
    call("forget", {"key": "m-fe"})
    assert call("recall", {"key": "m-fe"})["found"] is False, "forgotten key still recalled"


def _count(call, metric):
    return call("query", {"metric": metric})


def t_observe_idempotent(call, cat):
    m = sorted(cat)[0]
    before = _count(call, m)
    obs = {"observation_id": "o-idem", "metric": m, "value": 1}
    call("observe", obs)
    call("observe", obs)
    after = _count(call, m)
    assert after["count"] - before["count"] == 1, f"observation counted {after['count'] - before['count']} times"


def t_observe_durable(call, cat):
    m = sorted(cat)[0]
    before = _count(call, m)
    call("observe", {"observation_id": "o-dur", "metric": m, "value": 5})
    after = _count(call, m)
    assert after["count"] - before["count"] == 1 and after["sum"] - before["sum"] == 5, "query does not show the observation"


def t_observe_unknown(call, cat):
    _expect_error(call, "unknown-metric", "observe", {"observation_id": "o-unk", "metric": "no-such-metric-xyz", "value": 1})


def t_query_read_only(call, cat):
    m = sorted(cat)[0]
    assert _count(call, m) == _count(call, m), "repeat read differs"


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
    ("Identity", "revoke", "idempotent"): t_revoke_idempotent,
    ("Identity", "revoke", "revocation-effective"): t_revoke_effective,
    ("Identity", "verify", "read-only"): t_verify_read_only,
    ("Identity", "list", "read-only"): t_list_read_only,
    ("Instances", "acquire", "requirements-honoured"): t_acquire_honoured,
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


# ------------------------------------------------------------------ validator


def validate_contract(doc, catalog=None):
    """Return the errors that make a port contract unusable. An empty list means valid."""
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
    for name in PORTS[port]:
        if name not in ops:
            errs.append(f"{port}: missing operation '{name}'")
    for name in ops:
        if name not in PORTS[port]:
            errs.append(f"{port}: unexpected operation '{name}'")
    for name, op in ops.items():
        if name not in PORTS[port]:
            continue
        where = f"{port}.{name}"
        if not isinstance(op, dict):
            errs.append(f"{where}: must be an object")
            continue
        for part in PARTS:
            if part not in op:
                errs.append(f"{where}: missing part: {part}")
        if "name" in op and op["name"] != name:
            errs.append(f"{where}: name is {op['name']!r}")
        inp, outp = op.get("input"), op.get("output")
        if "input" in op:
            if not isinstance(inp, dict) or inp.get("type") != "object":
                errs.append(f"{where}: input must be an object schema")
            else:
                if inp.get("additionalProperties") is not False:
                    errs.append(f"{where}: input must set additionalProperties false")
                if not set(inp.get("required", [])) <= set(inp.get("properties", {})):
                    errs.append(f"{where}: input requires a property it does not declare")
        if "output" in op and (not isinstance(outp, dict) or outp.get("type") != "object"):
            errs.append(f"{where}: output must be an object schema")
        req = op.get("requirements")
        if "requirements" in op:
            if not isinstance(req, dict):
                errs.append(f"{where}: requirements must be an object")
            else:
                for key in req:
                    if key not in REQUIREMENT_KEYS:
                        errs.append(f"{where}: requirements: '{key}' is not one of {list(REQUIREMENT_KEYS)}")
        guar = op.get("guarantees")
        if "guarantees" in op:
            if not isinstance(guar, list) or not all(isinstance(g, str) for g in guar):
                errs.append(f"{where}: guarantees must be a list of strings")
            else:
                for g in guar:
                    if (port, name, g) not in GUARANTEE_TESTS:
                        errs.append(f"{where}: guarantee '{g}' has no conformance test")
        codes = op.get("errors")
        if "errors" in op:
            if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
                errs.append(f"{where}: errors must be a list of strings")
            elif "invalid-input" not in codes:
                errs.append(f"{where}: errors must include 'invalid-input'")
        mets = op.get("metrics")
        if "metrics" in op:
            if not isinstance(mets, list) or not all(isinstance(m, str) for m in mets):
                errs.append(f"{where}: metrics must be a list of strings")
            else:
                for m in mets:
                    if m not in names:
                        errs.append(f"{where}: metrics: '{m}' is not a name in the catalog")
    return errs


# ------------------------------------------------------------------ harness


def run_port(contract, adapter, catalog=None):
    """Run every declared guarantee test and the generic checks. Returns failure strings, empty on a pass."""
    cat = list(CATALOG_NAMES if catalog is None else catalog)
    port, ops = contract["port"], contract["operations"]
    failures = []

    def checked(op):
        spec = ops[op]

        def call(name, inp):
            assert name in ops, f"operation '{name}' not in the contract"
            sch = ops[name]
            bad = check_schema(inp, sch["input"])
            assert not bad, f"harness input for {name}: {bad[0]}"
            try:
                out = adapter.call(name, inp)
            except PortError as e:
                assert e.code in sch["errors"], f"undeclared error code '{e.code}' from {name}"
                raise
            bad = check_schema(out, sch["output"])
            assert not bad, f"{name} output: {bad[0]}"
            return out

        return call

    for op, spec in ops.items():
        label = f"{port}.{op}"
        try:
            adapter.call(op, {"__unexpected__": 1})
            failures.append(f"{label}: invalid-input: accepted an input outside the schema")
        except PortError as e:
            if e.code != "invalid-input":
                failures.append(f"{label}: invalid-input: refused with '{e.code}'")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{label}: invalid-input: raised {type(e).__name__}: {e}")
        for g in spec["guarantees"]:
            test = GUARANTEE_TESTS.get((port, op, g))
            if test is None:
                failures.append(f"{label}: {g}: no conformance test")
                continue
            try:
                test(checked(op), cat)
            except AssertionError as e:
                failures.append(f"{label}: {g}: {e}")
            except PortError as e:
                failures.append(f"{label}: {g}: unexpected error {e.code}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{label}: {g}: raised {type(e).__name__}: {e}")
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
        files = sorted(Path(directory).glob("*.json"))
        docs = [(f.name, json.loads(f.read_text())) for f in files]
    except (OSError, ValueError, IndexError, KeyError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    errs = []
    seen = set()
    for name, doc in docs:
        errs += [f"{name}: {e}" for e in validate_contract(doc, catalog)]
        if isinstance(doc, dict):
            seen.add(doc.get("port"))
    errs += [f"{directory}: no contract for port '{p}'" for p in PORTS if p not in seen]
    for e in errs:
        print(e)
    if not errs:
        print(f"ok: {len(docs)} contracts")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
