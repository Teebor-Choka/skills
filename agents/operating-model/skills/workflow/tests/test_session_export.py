import json
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import session_export as se  # noqa: E402

SCHEMA = HERE.parent / "schemas" / "session" / "record.schema.json"
SID = "00000000-0000-0000-0000-00000000aaaa"
FAKE_KEY = "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE1234"
FAKE_PAT = "github_pat_" + "A1b2C3d4E5" * 3
RED = "[REDACTED]"


def _base(uuid, parent, ty, ts, **flags):
    return {
        "parentUuid": parent, "isSidechain": False, "type": ty, "uuid": uuid,
        "timestamp": ts, "sessionId": SID, "cwd": "/work/demo",
        "version": "0.0.0", "gitBranch": "main", "userType": "external", **flags,
    }


def native_lines():
    """Hand-made session in Claude Code's JSONL shape. All content is invented."""
    out = [
        {"type": "mode", "mode": "normal", "sessionId": SID},
        {"type": "file-history-snapshot", "messageId": "m0", "snapshot": {}},
    ]
    u = _base("u1", None, "user", "T00")
    u["message"] = {"role": "user", "content": "list the files"}
    out.append(u)
    a = _base("a1", "u1", "assistant", "T01")
    a["message"] = {"role": "assistant", "model": "model-x",
                    "content": [{"type": "thinking", "thinking": "hmm", "signature": "s"}]}
    out.append(a)
    a = _base("a2", "a1", "assistant", "T02")
    a["message"] = {"role": "assistant", "model": "model-x", "content": [
        {"type": "redacted_thinking", "data": "xx"},
        {"type": "text", "text": "I will run ls."}]}
    out.append(a)
    a = _base("a3", "a2", "assistant", "T03")
    a["message"] = {"role": "assistant", "model": "model-x", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Bash",
         "input": {"command": "ls", "env": {"API_KEY": FAKE_KEY}}}]}
    out.append(a)
    r = _base("r1", "a3", "user", "T04")
    r["message"] = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_1",
         "content": "a.txt\nb.txt\ntoken=" + FAKE_KEY, "is_error": False}]}
    out.append(r)
    r = _base("r2", "r1", "user", "T05", isSidechain=True)
    r["message"] = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_2",
         "content": [{"type": "text", "text": "boom"}, {"type": "image", "source": {}}],
         "is_error": True}]}
    out.append(r)
    s = _base("s1", "r2", "system", "T06", isMeta=True)
    s.update({"subtype": "informational", "content": "note", "level": "info"})
    out.append(s)
    c = _base("c1", None, "user", "T07", isCompactSummary=True)
    c["message"] = {"role": "user", "content": "Summary of earlier turns."}
    out.append(c)
    u = _base("u2", "c1", "user", "T08")
    u["message"] = {"role": "user", "content": [
        {"type": "image", "source": {}}, {"type": "text", "text": "see"}]}
    out.append(u)
    a = _base("a4", "u2", "assistant", "T09")
    a["message"] = {"role": "assistant", "model": "model-x", "content": [
        {"type": "server_tool_use", "id": "srv1", "name": "web_search", "input": {}},
        {"type": "web_search_tool_result", "tool_use_id": "srv1", "content": []},
        {"type": "text", "text": "done"}]}
    out.append(a)
    u = _base("u3", "a4", "user", "T10")
    u["message"] = {"role": "user", "content": [{"type": "document", "source": {}}]}
    out.append(u)
    out.append({"type": "summary", "summary": "Legacy summary.", "leafUuid": "x"})
    out.append({"type": "future-thing", "payload": "do-not-copy"})
    out.append({"type": "ai-title", "aiTitle": "demo", "sessionId": SID})
    return out


def write_native(path, lines):
    path.write_bytes(("\n".join(json.dumps(x) for x in lines) + "\n").encode())
    return path


@pytest.fixture
def native(tmp_path):
    p = write_native(tmp_path / "session.jsonl", native_lines())
    with p.open("a") as f:
        f.write("[1, 2]\n")  # a non-object line
    return p


def R(seq, kind, uuid, parent, ts, bi, side=False, meta=False, sid=SID, **extra):
    return {"schema_version": "1", "harness": "claude-code", "session_id": sid, "seq": seq,
            "uuid": uuid, "parent_uuid": parent, "timestamp": ts, "kind": kind,
            "block_index": bi, "is_sidechain": side, "is_meta": meta, **extra}


EXPECTED = [
    R(0, "user", "u1", None, "T00", 0, text="list the files"),
    R(1, "assistant_text", "a2", "a1", "T02", 1, text="I will run ls.", model="model-x"),
    R(2, "tool_call", "a3", "a2", "T03", 0, tool_use_id="toolu_1", name="Bash",
      input={"command": "ls", "env": {"API_KEY": RED}}),
    R(3, "tool_result", "r1", "a3", "T04", 0, tool_use_id="toolu_1",
      content="a.txt\nb.txt\ntoken=" + RED, is_error=False),
    R(4, "tool_result", "r2", "r1", "T05", 0, side=True, tool_use_id="toolu_2",
      content="boom\n[image omitted]", is_error=True),
    R(5, "system", "s1", "r2", "T06", 0, meta=True, subtype="informational", content="note"),
    R(6, "compaction", "c1", None, "T07", 0, text="Summary of earlier turns."),
    R(7, "user", "u2", "c1", "T08", 1, text="see"),
    R(8, "assistant_text", "a4", "u2", "T09", 2, text="done", model="model-x"),
    R(9, "compaction", None, None, None, 0, sid=None, text="Legacy summary."),
    R(10, "system", None, None, None, 0, sid=None, subtype="unknown-line", content="future-thing"),
]

EXPECTED_DROPS = {
    "bookkeeping": 3, "thinking": 1, "redacted_thinking": 1, "tool_result_non_text": 1,
    "user_image": 1, "server_tool_use": 1, "web_search_tool_result": 1, "document": 1,
    "non_object_line": 1, "unknown_line": 1,
}


def by_kind(records):
    out = {}
    for r in records:
        out.setdefault(r["kind"], []).append(r)
    return out


# ---- Acceptance 1: schema, one field list per kind ---------------------------

EXPECTED_KINDS = {"user", "assistant_text", "tool_call", "tool_result", "system", "compaction"}
JSON_TO_SPEC = {"string": se.STR, "integer": se.INT, "boolean": se.BOOL, "object": se.OBJ}


def _spec_of(prop):
    if "const" in prop:
        return se.STR
    t = prop["type"]
    if isinstance(t, list):
        assert sorted(t) == ["null", "string"], prop
        return se.STR_OR_NONE
    return JSON_TO_SPEC[t]


def test_validator_defines_exactly_the_expected_kinds():
    assert set(se.KINDS) == EXPECTED_KINDS


def test_schema_matches_validator_on_names_types_and_minimum():
    schema = json.loads(SCHEMA.read_text())
    branches = {b["properties"]["kind"]["const"]: b for b in schema["oneOf"]}
    assert set(branches) == EXPECTED_KINDS
    for kind, b in branches.items():
        fields = {**se.COMMON, **se.KINDS[kind]["required"]}
        assert set(b["properties"]) == set(fields), kind
        assert set(b["required"]) == set(fields), kind
        assert b["additionalProperties"] is False
        for name, prop in b["properties"].items():
            if name != "kind":
                assert _spec_of(prop) == fields[name], (kind, name)
            assert prop.get("minimum") == se.MINIMUM.get(name), (kind, name)


def test_every_record_kind_carries_the_flags_and_block_index():
    for name in ("is_sidechain", "is_meta", "block_index"):
        assert name in se.COMMON


def test_exported_records_validate_against_schema_when_jsonschema_present(native):
    jsonschema = pytest.importorskip("jsonschema", reason="optional: jsonschema not installed")
    schema = json.loads(SCHEMA.read_text())
    for r in se.session_export(native):
        jsonschema.validate(r, schema)


# ---- Acceptance 2: literal expected export, round trip ------------------------

def test_export_equals_the_expected_literal(native):
    assert list(se.session_export(native)) == EXPECTED


def test_export_returns_a_list_with_drop_counts_by_reason(native):
    recs = se.session_export(native)
    assert isinstance(recs, list)
    assert dict(recs.dropped) == EXPECTED_DROPS


def test_thinking_text_never_reaches_a_record(native):
    assert "hmm" not in json.dumps(list(se.session_export(native)))


def test_unknown_line_keeps_only_its_type_name(native):
    assert "do-not-copy" not in json.dumps(list(se.session_export(native)))


def test_round_trip_every_field_equal(native, tmp_path):
    recs = se.session_export(native)
    out = tmp_path / "record.jsonl"
    se.write_records(recs, out)
    assert se.load_records(out) == EXPECTED


def test_breaking_the_uuid_mapping_is_detected(native):
    recs = list(se.session_export(native))
    recs[0] = {**recs[0], "uuid": "wrong"}
    assert recs != EXPECTED


def test_multi_block_line_shares_uuid_and_numbers_blocks(tmp_path):
    a = _base("m1", None, "assistant", "T")
    a["message"] = {"role": "assistant", "model": "m", "content": [
        {"type": "text", "text": "one"},
        {"type": "tool_use", "id": "t", "name": "N", "input": {}},
        {"type": "text", "text": "two"}]}
    recs = se.session_export(write_native(tmp_path / "s.jsonl", [a]))
    assert [(r["uuid"], r["block_index"]) for r in recs] == [("m1", 0), ("m1", 1), ("m1", 2)]


def test_tool_input_that_is_not_an_object_is_kept_as_redacted_raw(tmp_path):
    a = _base("m1", None, "assistant", "T")
    a["message"] = {"role": "assistant", "model": "m", "content": [
        {"type": "tool_use", "id": "t", "name": "N", "input": "token=" + FAKE_KEY}]}
    recs = se.session_export(write_native(tmp_path / "s.jsonl", [a]))
    assert recs[0]["input"] == {"_raw": "token=" + RED}


def test_every_exported_record_passes_the_stdlib_validator(native):
    for r in se.session_export(native):
        se.validate_record(r)


def test_missing_or_null_ids_become_null_and_wrong_types_raise(tmp_path):
    u = {"type": "user", "uuid": None, "message": {"role": "user", "content": "hi"}}
    rec = se.session_export(write_native(tmp_path / "a.jsonl", [u]))[0]
    assert (rec["uuid"], rec["session_id"], rec["timestamp"], rec["parent_uuid"]) == (None,) * 4
    bad = {"type": "user", "uuid": 5, "message": {"role": "user", "content": "hi"}}
    with pytest.raises(ValueError, match="line 1"):
        se.session_export(write_native(tmp_path / "b.jsonl", [bad]))


# ---- Loader and validator boundaries -----------------------------------------

def good():
    return {"schema_version": "1", "harness": "claude-code", "session_id": "s", "seq": 0,
            "uuid": "u", "parent_uuid": None, "timestamp": "t", "kind": "user",
            "block_index": 0, "is_sidechain": False, "is_meta": False, "text": "hi"}


BAD = [
    lambda r: r.pop("text"),
    lambda r: r.pop("kind"),
    lambda r: r.pop("is_sidechain"),
    lambda r: r.pop("block_index"),
    lambda r: r.update(kind="bogus"),
    lambda r: r.update(text=5),
    lambda r: r.update(extra=1),
    lambda r: r.update(seq="0"),
    lambda r: r.update(seq=True),
    lambda r: r.update(seq=-1),
    lambda r: r.update(block_index=-1),
    lambda r: r.update(is_meta="no"),
    lambda r: r.update(schema_version="2"),
]


def test_validator_accepts_a_good_record():
    se.validate_record(good())


@pytest.mark.parametrize("mutate", BAD)
def test_validator_rejects_bad_records(mutate):
    r = good()
    mutate(r)
    with pytest.raises(ValueError):
        se.validate_record(r)


@pytest.mark.parametrize("mutate", BAD)
def test_schema_file_rejects_the_same_bad_records(mutate):
    jsonschema = pytest.importorskip("jsonschema", reason="optional: jsonschema not installed")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(good(), schema)
    r = good()
    mutate(r)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(r, schema)


def test_load_records_rejects_an_invalid_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps({"kind": "user"}) + "\n")
    with pytest.raises(ValueError, match="line 1"):
        se.load_records(p)


def test_empty_session_is_an_error_not_an_empty_list(tmp_path):
    p = write_native(tmp_path / "empty.jsonl", [{"type": "mode", "mode": "x"}])
    with pytest.raises(ValueError, match="no exportable"):
        se.session_export(p)


# ---- Malformed input ---------------------------------------------------------

def test_a_bad_line_that_is_not_the_last_raises_with_its_number(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(b'{"type": "mode"}\n{not json\n{"type": "mode"}\n')
    with pytest.raises(ValueError, match="line 2"):
        se.session_export(p)


def test_a_bad_final_line_with_a_newline_still_raises(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(json.dumps(native_lines()[2]).encode() + b"\n{not json\n")
    with pytest.raises(ValueError, match="line 2"):
        se.session_export(p)


def test_truncated_final_line_is_skipped_with_count_and_warning(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(json.dumps(native_lines()[2]).encode() + b'\n{"type": "user", "mess')
    with pytest.warns(UserWarning, match="truncated"):
        recs = se.session_export(p)
    assert len(recs) == 1 and recs.dropped["truncated_final_line"] == 1


def test_final_line_without_newline_but_valid_is_processed(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(json.dumps(native_lines()[2]).encode())
    assert len(se.session_export(p)) == 1


def test_invalid_utf8_raises_with_line_number(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(b'{"type": "mode"}\n\xff\xfe\n')
    with pytest.raises(ValueError, match="line 2"):
        se.session_export(p)


def test_deep_nesting_is_a_clear_error(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_bytes(b"[" * 200000 + b"\n")
    with pytest.raises(ValueError, match="line 1"):
        se.session_export(p)


def test_missing_file_and_directory_raise_oserror(tmp_path):
    for fn in (se.session_export, se.load_records):
        with pytest.raises(FileNotFoundError):
            fn(tmp_path / "nope.jsonl")
        with pytest.raises(OSError):
            fn(tmp_path)


def test_lone_surrogate_leaves_no_partial_output(tmp_path):
    out = tmp_path / "out.jsonl"
    r = good()
    r["text"] = "\ud800"
    with pytest.raises(ValueError):
        se.write_records([good(), r], out)
    assert list(tmp_path.iterdir()) == []


def test_write_records_replaces_existing_file_atomically(tmp_path):
    out = tmp_path / "out.jsonl"
    out.write_text("old\n")
    se.write_records([good()], out)
    assert se.load_records(out) == [good()]
    assert [p.name for p in tmp_path.iterdir()] == ["out.jsonl"]


def test_cli_prints_drop_counts_to_stderr(native, tmp_path, capsys):
    out = tmp_path / "o.jsonl"
    assert se.main([str(native), str(out)]) == 0
    err = capsys.readouterr().err
    assert "dropped thinking: 1" in err and "dropped bookkeeping: 3" in err
    assert se.load_records(out) == EXPECTED


def test_cli_reports_a_missing_file_with_exit_1(tmp_path, capsys):
    assert se.main([str(tmp_path / "nope"), str(tmp_path / "o")]) == 1
    assert "error:" in capsys.readouterr().err


# ---- Acceptance 3 [A]: other harnesses refuse ---------------------------------

@pytest.mark.parametrize("harness", ["codex", "opencode"])
def test_unverified_harnesses_raise_unsupported(harness, native):
    with pytest.raises(se.UnsupportedFormatError, match="unsupported format: not verified"):
        se.session_export(native, harness=harness)


def test_unknown_harness_is_rejected(native):
    with pytest.raises(se.UnsupportedFormatError):
        se.session_export(native, harness="nope")


# ---- Acceptance 4: redaction -------------------------------------------------

def test_fake_key_is_absent_from_every_exported_record(native):
    blob = json.dumps(list(se.session_export(native)))
    assert FAKE_KEY not in blob
    assert RED in blob


def test_sk_pattern_alone_catches_a_bare_key():
    assert se.redact("x " + FAKE_KEY + " y") == "x " + RED + " y"


def test_github_pat_is_redacted():
    assert se.redact("x " + FAKE_PAT + " y") == "x " + RED + " y"


@pytest.mark.parametrize("secret,expected", [
    ("ghp_" + "a" * 36, RED),
    ("AKIA" + "A" * 16, RED),
    ("xoxb-1234567890-abcdefghij", RED),
    ("Bearer abcdefghijklmnop12345678", RED),
    ("Bearer abc123xyz", RED),
    ("password=hunter2hunter2", "password=" + RED),
    ("DB_PASSWORD=hunter2", "DB_PASSWORD=" + RED),
    ("export GITHUB_TOKEN=abc", "export GITHUB_TOKEN=" + RED),
    ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI", "AWS_SECRET_ACCESS_KEY=" + RED),
    ("MY_API_KEY=xyz", "MY_API_KEY=" + RED),
    ('{"password": "hunter2"}', '{"password": "' + RED + '"}'),
    ("Authorization: Basic dXNlcjpwYXNz", "Authorization: " + RED),
    ("authorization=Bearer abc", "authorization=" + RED),
    ("git clone https://user:pass@github.com/org/repo.git",
     "git clone https://" + RED + "@github.com/org/repo.git"),
    ("-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBg\n-----END PRIVATE KEY-----", RED),
])
def test_redact_covers_secret_shapes_exactly(secret, expected):
    assert se.redact("before " + secret + " after") == "before " + expected + " after"


def test_unterminated_private_key_is_redacted_to_the_end():
    text = "before -----BEGIN RSA PRIVATE KEY-----\nMIIBVQIBADANBg\nmore"
    assert se.redact(text) == "before " + RED


def test_redact_leaves_plain_text_and_ssh_user_alone():
    for s in ("list the files in src/", "ssh://git@github.com/org/repo", "tokens are fine"):
        assert se.redact(s) == s


def test_redact_is_linear_on_hostile_input():
    t = time.time()
    se.redact("-----BEGIN PRIVATE KEY-----\n" * 20000)
    se.redact("a" * 200000)
    se.redact("-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----\n" * 5000)
    assert time.time() - t < 5


def test_redaction_reaches_nested_tool_input(native):
    call = by_kind(se.session_export(native))["tool_call"][0]
    assert call["input"]["env"]["API_KEY"] == RED
    assert call["input"]["command"] == "ls"


def test_secret_looking_keys_redact_any_value_type():
    out = se._redact_value({"password": {"value": "x"}, "secrets": ["x"], "token": 123456,
                            "api_key": None, "name": "ok", "n": 3})
    assert out == {"password": RED, "secrets": RED, "token": RED,
                   "api_key": None, "name": "ok", "n": 3}


def test_dict_keys_that_are_secrets_are_redacted():
    out = se._redact_value({FAKE_KEY: "v", "k": {"ghp_" + "a" * 36: 1}})
    assert FAKE_KEY not in json.dumps(out)
    assert list(out.values())[0] == "v"


def test_colliding_redacted_keys_do_not_lose_values():
    out = se._redact_value({FAKE_KEY: 1, FAKE_KEY + "z": 2})
    assert sorted(out.values()) == [1, 2]


def test_envelope_fields_are_redacted_too(tmp_path):
    u = _base(FAKE_KEY, FAKE_KEY + "p", "user", "T")
    u["sessionId"] = FAKE_KEY
    u["message"] = {"role": "user", "content": "hi"}
    rec = se.session_export(write_native(tmp_path / "s.jsonl", [u]))[0]
    assert FAKE_KEY not in json.dumps(rec)
    assert rec["uuid"] == RED and rec["session_id"] == RED


# ---- review 2: redaction must not stop early ---------------------------------

@pytest.mark.parametrize("text,expected", [
    ("curl https://user:s3cr3tP@ssw0rd!@host/x", "curl https://" + RED + "@host/x"),
    ("https://u:p@a@b@host/x", "https://" + RED + "@host/x"),
    ("https://user:p%40ss@host/x", "https://" + RED + "@host/x"),
    ("https://u:pw@host/x?e=a@b", "https://" + RED + "@host/x?e=a@b"),
    ("https://u:pw@host", "https://" + RED + "@host"),
    ("https://user@host/x", "https://user@host/x"),
    ("ssh://git@host/x", "ssh://git@host/x"),
    ("see https://example.com/a@b and me@x.com", "see https://example.com/a@b and me@x.com"),
])
def test_url_userinfo_is_redacted_up_to_the_last_at_sign(text, expected):
    assert se.redact(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Bearer abc def", "Bearer abc def".replace("Bearer abc", RED)),
    ("Bearer abc", RED),
    ("password: hunter two", "password: " + RED),
    ("password: hunter two\nnext line", "password: " + RED + "\nnext line"),
    ("password=hunter two", "password=" + RED + " two"),
    ('password: "a b @c"', 'password: "' + RED + '"'),
    ('{"password": "pa\\"ss tail"}', '{"password": "' + RED + '"}'),
    ("password: 'it\\'s tail'", "password: '" + RED + "'"),
    ("Authorization: Bearer abc def ghi", "Authorization: " + RED + " def ghi"),
    ("Authorization: Basic dXNlcjpwYXNz extra", "Authorization: " + RED + " extra"),
])
def test_other_patterns_do_not_leak_a_tail(text, expected):
    assert se.redact(text) == expected
