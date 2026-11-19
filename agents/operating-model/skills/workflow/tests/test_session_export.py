import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import session_export as se  # noqa: E402

SCHEMA = HERE.parent / "schemas" / "session" / "record.schema.json"
SID = "00000000-0000-0000-0000-00000000aaaa"
FAKE_KEY = "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE1234"


def _base(uuid, parent, ty, ts):
    return {
        "parentUuid": parent, "isSidechain": False, "type": ty, "uuid": uuid,
        "timestamp": ts, "sessionId": SID, "cwd": "/work/demo",
        "version": "0.0.0", "gitBranch": "main", "userType": "external",
    }


def native_lines():
    """Hand-made session in Claude Code's JSONL shape. All content is invented."""
    out = [
        {"type": "mode", "mode": "normal", "sessionId": SID},
        {"type": "file-history-snapshot", "messageId": "m0", "snapshot": {}},
    ]
    u = _base("u1", None, "user", "2026-01-01T00:00:00.000Z")
    u["message"] = {"role": "user", "content": "list the files"}
    out.append(u)
    a = _base("a1", "u1", "assistant", "2026-01-01T00:00:01.000Z")
    a["message"] = {"role": "assistant", "model": "model-x",
                    "content": [{"type": "thinking", "thinking": "hmm", "signature": "s"}]}
    out.append(a)
    a = _base("a2", "a1", "assistant", "2026-01-01T00:00:02.000Z")
    a["message"] = {"role": "assistant", "model": "model-x",
                    "content": [{"type": "text", "text": "I will run ls."}]}
    out.append(a)
    a = _base("a3", "a2", "assistant", "2026-01-01T00:00:03.000Z")
    a["message"] = {"role": "assistant", "model": "model-x", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Bash",
         "input": {"command": "ls", "env": {"API_KEY": FAKE_KEY}}}]}
    out.append(a)
    r = _base("r1", "a3", "user", "2026-01-01T00:00:04.000Z")
    r["message"] = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_1",
         "content": "a.txt\nb.txt\ntoken=" + FAKE_KEY, "is_error": False}]}
    out.append(r)
    r = _base("r2", "r1", "user", "2026-01-01T00:00:05.000Z")
    r["message"] = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_2",
         "content": [{"type": "text", "text": "boom"}], "is_error": True}]}
    out.append(r)
    s = _base("s1", "r2", "system", "2026-01-01T00:00:06.000Z")
    s.update({"subtype": "informational", "content": "note", "level": "info"})
    out.append(s)
    c = _base("c1", None, "user", "2026-01-01T00:00:07.000Z")
    c["isCompactSummary"] = True
    c["message"] = {"role": "user", "content": "Summary of earlier turns."}
    out.append(c)
    out.append({"type": "ai-title", "aiTitle": "demo", "sessionId": SID})
    return out


@pytest.fixture
def native(tmp_path):
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in native_lines()) + "\n")
    return p


def by_kind(records):
    out = {}
    for r in records:
        out.setdefault(r["kind"], []).append(r)
    return out


# Acceptance 1: schema with one field list per kind.
EXPECTED_KINDS = {"user", "assistant_text", "tool_call", "tool_result", "system", "compaction"}


def test_validator_defines_exactly_the_expected_kinds():
    assert set(se.KINDS) == EXPECTED_KINDS


def test_schema_file_has_one_branch_per_kind_matching_the_validator():
    schema = json.loads(SCHEMA.read_text())
    branches = {b["properties"]["kind"]["const"]: b for b in schema["oneOf"]}
    assert set(branches) == EXPECTED_KINDS
    for kind, b in branches.items():
        assert set(b["required"]) == set(se.KINDS[kind]["required"]) | set(se.COMMON), kind
        assert b.get("additionalProperties") is False


def test_exported_records_validate_against_schema_when_jsonschema_present(native):
    jsonschema = pytest.importorskip("jsonschema", reason="optional: jsonschema not installed")
    schema = json.loads(SCHEMA.read_text())
    for r in se.session_export(native):
        jsonschema.validate(r, schema)


# Acceptance 2: export and re-import with every field equal.
def test_export_maps_each_kind(native):
    k = by_kind(se.session_export(native))
    assert set(k) == EXPECTED_KINDS
    assert k["user"][0]["text"] == "list the files"
    assert k["assistant_text"][0]["text"] == "I will run ls."
    assert k["assistant_text"][0]["model"] == "model-x"
    assert k["tool_call"][0]["name"] == "Bash"
    assert k["tool_call"][0]["tool_use_id"] == "toolu_1"
    assert k["tool_result"][0]["is_error"] is False
    assert k["tool_result"][1]["is_error"] is True
    assert k["tool_result"][1]["content"] == "boom"
    assert k["system"][0]["subtype"] == "informational"
    assert k["compaction"][0]["text"] == "Summary of earlier turns."


def test_export_skips_thinking_and_bookkeeping_lines(native):
    recs = se.session_export(native)
    assert len(recs) == 7
    assert all("hmm" not in json.dumps(r) for r in recs)


def test_export_keeps_file_order_with_sequential_seq(native):
    recs = se.session_export(native)
    assert [r["seq"] for r in recs] == list(range(len(recs)))
    assert [r["kind"] for r in recs] == [
        "user", "assistant_text", "tool_call", "tool_result", "tool_result",
        "system", "compaction"]


def test_round_trip_every_field_equal(native, tmp_path):
    recs = se.session_export(native)
    out = tmp_path / "record.jsonl"
    se.write_records(recs, out)
    assert se.load_records(out) == recs


def test_every_exported_record_passes_the_stdlib_validator(native):
    for r in se.session_export(native):
        se.validate_record(r)


# Loader rejects bad records (boundaries).
def good():
    return {"schema_version": "1", "harness": "claude-code", "session_id": "s", "seq": 0,
            "uuid": "u", "parent_uuid": None, "timestamp": "t", "kind": "user", "text": "hi"}


def test_validator_accepts_a_good_record():
    se.validate_record(good())


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("text"),
    lambda r: r.pop("kind"),
    lambda r: r.update(kind="bogus"),
    lambda r: r.update(text=5),
    lambda r: r.update(extra=1),
    lambda r: r.update(seq="0"),
    lambda r: r.update(seq=True),
    lambda r: r.update(schema_version="2"),
])
def test_validator_rejects_bad_records(mutate):
    r = good()
    mutate(r)
    with pytest.raises(ValueError):
        se.validate_record(r)


def test_load_records_rejects_an_invalid_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps({"kind": "user"}) + "\n")
    with pytest.raises(ValueError):
        se.load_records(p)


def test_empty_session_is_an_error_not_an_empty_list(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text(json.dumps({"type": "mode", "mode": "x", "sessionId": SID}) + "\n")
    with pytest.raises(ValueError, match="no exportable"):
        se.session_export(p)


def test_malformed_json_line_is_an_error_naming_the_line(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text("{not json\n")
    with pytest.raises(ValueError, match="line 1"):
        se.session_export(p)


# Acceptance 3 [A]: other harnesses refuse instead of returning an empty record.
@pytest.mark.parametrize("harness", ["codex", "opencode"])
def test_unverified_harnesses_raise_unsupported(harness, native):
    with pytest.raises(se.UnsupportedFormatError, match="unsupported format: not verified"):
        se.session_export(native, harness=harness)


def test_unknown_harness_is_rejected(native):
    with pytest.raises(se.UnsupportedFormatError):
        se.session_export(native, harness="nope")


# Acceptance 4: redaction.
def test_fake_key_is_absent_from_every_exported_record(native):
    blob = json.dumps(se.session_export(native))
    assert FAKE_KEY not in blob
    assert "[REDACTED]" in blob


@pytest.mark.parametrize("secret", [
    "ghp_" + "a" * 36,
    "AKIA" + "A" * 16,
    "Bearer abcdefghijklmnop12345678",
    "-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBg\n-----END PRIVATE KEY-----",
    "password=hunter2hunter2",
    "xoxb-1234567890-abcdefghij",
])
def test_redact_covers_common_secret_shapes(secret):
    out = se.redact("before " + secret + " after")
    assert out.startswith("before ") and out.endswith(" after")
    assert "[REDACTED]" in out
    assert secret.split("=")[-1][:12] not in out or "=" not in secret


def test_redact_leaves_plain_text_alone():
    assert se.redact("list the files in src/") == "list the files in src/"


def test_redaction_reaches_nested_tool_input(native):
    call = by_kind(se.session_export(native))["tool_call"][0]
    assert call["input"]["env"]["API_KEY"] == "[REDACTED]"
    assert call["input"]["command"] == "ls"
