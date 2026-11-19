"""Standard session record and the Claude Code extractor (decision D22).

Every harness keeps its session in a native format. An adapter exports it to
one record format, one JSON object per line, so any run can be read and
replayed. The schema is documented in schemas/session/record.schema.json. The
loader here checks records with the standard library only.

Only the Claude Code adapter is verified. Codex and OpenCode formats are not
verified (see the format research), so their adapters refuse.

Drops are never silent: session_export returns a list that carries a
`dropped` Counter keyed by reason. `(uuid, block_index)` is the record key,
because one native line can hold several blocks.
"""
import json
import os
import re
import sys
import tempfile
import warnings
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = "1"
HARNESS = "claude-code"
UNSUPPORTED = "unsupported format: not verified"

STR, STR_OR_NONE, INT, BOOL, OBJ = "str", "str|None", "int", "bool", "object"

COMMON = {
    "schema_version": STR, "harness": STR, "session_id": STR_OR_NONE, "seq": INT,
    "uuid": STR_OR_NONE, "parent_uuid": STR_OR_NONE, "timestamp": STR_OR_NONE,
    "kind": STR, "block_index": INT, "is_sidechain": BOOL, "is_meta": BOOL,
}
MINIMUM = {"seq": 0, "block_index": 0}

KINDS = {
    "user": {"required": {"text": STR}},
    "assistant_text": {"required": {"text": STR, "model": STR_OR_NONE}},
    "tool_call": {"required": {"tool_use_id": STR, "name": STR, "input": OBJ}},
    "tool_result": {"required": {"tool_use_id": STR, "content": STR, "is_error": BOOL}},
    "system": {"required": {"subtype": STR_OR_NONE, "content": STR}},
    "compaction": {"required": {"text": STR}},
}


class UnsupportedFormatError(Exception):
    pass


class Export(list):
    """The exported records, plus `dropped`: a Counter of dropped items by reason."""

    def __init__(self, *a):
        super().__init__(*a)
        self.dropped = Counter()


# ---- redaction --------------------------------------------------------------

REDACTED = "[REDACTED]"
_KW = r"(?:password|passwd|passphrase|secret|token|api[_-]?key|private[_-]?key|credential)"
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_AUTH = re.compile(
    r"(?i)(\bauthorization[\"']?\s*[:=]\s*)(?:(?:basic|bearer|token|digest)\s+)?"
    r"(\"[^\"]*\"|'[^']*'|[^\s\"']+)")
_KV = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]*" + _KW + r"[A-Za-z0-9_.-]*[\"']?\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s\"']+)")
_TOKENS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
]
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{4,}")
_SECRET_KEY = re.compile(r"(?i)(passw|secret|token|api[_-]?key|private[_-]?key|credential)")


def _keep_value_quotes(m):
    val = m.group(2)
    q = val[0] if val[:1] in "\"'" else ""
    return m.group(1) + q + REDACTED + q


def _redact_pem(text):
    """Redact PEM private keys. An unterminated key is redacted to the end. Linear."""
    if "-----BEGIN" not in text:
        return text
    parts, pos = [], 0
    while True:
        m = _PEM_BEGIN.search(text, pos)
        if not m:
            break
        parts.append(text[pos:m.start()])
        parts.append(REDACTED)
        end = text.find("-----END", m.end())
        close = -1 if end == -1 else text.find("-----", end + 8)
        pos = len(text) if close == -1 else close + 5
    parts.append(text[pos:])
    return "".join(parts)


def redact(text):
    text = _redact_pem(text)
    text = _URL_CREDS.sub(lambda m: m.group(1) + REDACTED + "@", text)
    for p in _TOKENS:
        text = p.sub(REDACTED, text)
    text = _AUTH.sub(_keep_value_quotes, text)
    text = _BEARER.sub(REDACTED, text)
    return _KV.sub(_keep_value_quotes, text)


def _redact_value(v):
    """Redact every string in a JSON value. A secret-looking key redacts its value of any type."""
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, list):
        return [_redact_value(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            nk = redact(k) if isinstance(k, str) else k
            while nk in out:
                nk = f"{nk}_"
            secret = isinstance(k, str) and _SECRET_KEY.search(k) and x is not None
            out[nk] = REDACTED if secret else _redact_value(x)
        return out
    return v


# ---- validation and record files ---------------------------------------------

def _type_ok(value, spec):
    if spec == STR:
        return isinstance(value, str)
    if spec == STR_OR_NONE:
        return value is None or isinstance(value, str)
    if spec == INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if spec == BOOL:
        return isinstance(value, bool)
    return isinstance(value, dict)


def validate_record(record):
    """Raise ValueError when the record does not match the schema."""
    if not isinstance(record, dict):
        raise ValueError("record is not an object")
    kind = record.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    fields = {**COMMON, **KINDS[kind]["required"]}
    missing = sorted(set(fields) - set(record))
    if missing:
        raise ValueError(f"{kind}: missing fields {missing}")
    extra = sorted(set(record) - set(fields))
    if extra:
        raise ValueError(f"{kind}: unexpected fields {extra}")
    for name, spec in fields.items():
        if not _type_ok(record[name], spec):
            raise ValueError(f"{kind}.{name}: expected {spec}, got {type(record[name]).__name__}")
        if name in MINIMUM and record[name] < MINIMUM[name]:
            raise ValueError(f"{kind}.{name}: must be >= {MINIMUM[name]}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")


def _numbered_lines(path):
    """Yield (line number, raw bytes, decoded text) per non-blank line. Invalid UTF-8 raises."""
    with open(path, "rb") as f:
        for n, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                yield n, raw, raw.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError(f"{path}: line {n}: invalid UTF-8: {e}") from e


def _loads(text):
    try:
        return json.loads(text)
    except RecursionError:
        raise ValueError("JSON nested too deeply") from None


def write_records(records, path):
    """Validate and encode everything first, then replace the file atomically."""
    chunks = []
    for r in records:
        validate_record(r)
        chunks.append((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".session-export-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.writelines(chunks)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_records(path):
    out = []
    for n, _, text in _numbered_lines(path):
        try:
            r = _loads(text)
            validate_record(r)
        except ValueError as e:
            raise ValueError(f"{path}: line {n}: {e}") from e
        out.append(r)
    return out


# ---- Claude Code extractor --------------------------------------------------

BOOKKEEPING = {
    "mode", "permission-mode", "file-history-snapshot", "file-history-delta", "last-prompt",
    "ai-title", "agent-name", "queue-operation", "cost-state", "pr-link", "attachment",
    "atis-latch", "api-request", "api-request-shape", "api-request-blob",
}
DROPPED_BLOCKS = {"thinking", "redacted_thinking", "server_tool_use", "document",
                  "web_search_tool_result"}


def _opt_str(obj, key):
    v = obj.get(key)
    if v is not None and not isinstance(v, str):
        raise ValueError(f"{key} must be a string or null, got {type(v).__name__}")
    return v


def _str(v, what):
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{what} must be a string, got {type(v).__name__}")
    return v


def _result_text(content, dropped):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError(f"tool_result content must be a string or list, got {type(content).__name__}")
    parts = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(_str(b.get("text"), "tool_result text"))
        else:
            kind = b.get("type", "unknown") if isinstance(b, dict) else "unknown"
            parts.append(f"[{kind} omitted]")
            dropped["tool_result_non_text"] += 1
    return "\n".join(parts)


def _message_blocks(message):
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [(0, {"type": "text", "text": content})]
    if content is None:
        return []
    if not isinstance(content, list):
        raise ValueError(f"message content must be a string or list, got {type(content).__name__}")
    return list(enumerate(content))


def _line_records(obj, dropped):
    """Return [(kind, block_index, fields)] for one native line. Count anything dropped."""
    ty = obj.get("type")
    if ty == "system":
        return [("system", 0, {"subtype": _opt_str(obj, "subtype"),
                               "content": _str(obj.get("content"), "system content")})]
    if ty == "summary":
        return [("compaction", 0, {"text": _str(obj.get("summary"), "summary")})]
    if ty in BOOKKEEPING:
        dropped["bookkeeping"] += 1
        return []
    if ty not in ("user", "assistant"):
        dropped["unknown_line"] += 1
        return [("system", 0, {"subtype": "unknown-line",
                               "content": ty if isinstance(ty, str) else ""})]
    message = obj.get("message")
    out = []
    for i, b in _message_blocks(message):
        bt = b.get("type") if isinstance(b, dict) else None
        if bt in DROPPED_BLOCKS:
            dropped[bt] += 1
        elif ty == "user" and bt == "image":
            dropped["user_image"] += 1
        elif ty == "user" and bt == "text":
            kind = "compaction" if obj.get("isCompactSummary") else "user"
            out.append((kind, i, {"text": _str(b.get("text"), "text block")}))
        elif ty == "user" and bt == "tool_result":
            out.append(("tool_result", i, {
                "tool_use_id": _str(b.get("tool_use_id"), "tool_use_id"),
                "content": _result_text(b.get("content"), dropped),
                "is_error": bool(b.get("is_error", False)),
            }))
        elif ty == "assistant" and bt == "text":
            model = message.get("model") if isinstance(message, dict) else None
            out.append(("assistant_text", i, {
                "text": _str(b.get("text"), "text block"),
                "model": model if isinstance(model, str) else None}))
        elif ty == "assistant" and bt == "tool_use":
            inp = b.get("input")
            if inp is None:
                inp = {}
            elif not isinstance(inp, dict):
                inp = {"_raw": inp if isinstance(inp, str) else json.dumps(inp)}
            out.append(("tool_call", i, {
                "tool_use_id": _str(b.get("id"), "tool_use id"),
                "name": _str(b.get("name"), "tool_use name"), "input": inp}))
        else:
            dropped["unknown_block"] += 1
    return out


def _export_claude_code(native_path):
    records = Export()
    dropped = records.dropped
    for n, raw, text in _numbered_lines(native_path):
        try:
            try:
                obj = _loads(text)
            except json.JSONDecodeError as e:
                if raw.endswith(b"\n"):
                    raise ValueError(f"invalid JSON: {e}") from e
                warnings.warn(f"{native_path}: line {n}: truncated final line skipped",
                              UserWarning)
                dropped["truncated_final_line"] += 1
                continue
            if not isinstance(obj, dict):
                dropped["non_object_line"] += 1
                continue
            envelope = {
                "session_id": _opt_str(obj, "sessionId"), "uuid": _opt_str(obj, "uuid"),
                "parent_uuid": _opt_str(obj, "parentUuid"),
                "timestamp": _opt_str(obj, "timestamp"),
                "is_sidechain": bool(obj.get("isSidechain")), "is_meta": bool(obj.get("isMeta")),
            }
            for kind, bi, fields in _line_records(obj, dropped):
                rec = {"schema_version": SCHEMA_VERSION, "harness": HARNESS,
                       "seq": len(records), "kind": kind, "block_index": bi,
                       **envelope, **fields}
                rec = _redact_value(rec)
                validate_record(rec)
                records.append(rec)
        except RecursionError:
            raise ValueError(f"{native_path}: line {n}: JSON nested too deeply") from None
        except ValueError as e:
            raise ValueError(f"{native_path}: line {n}: {e}") from e
    if not records:
        raise ValueError(f"{native_path}: no exportable records")
    return records


def _export_unverified(native_path):
    raise UnsupportedFormatError(UNSUPPORTED)


ADAPTERS = {
    "claude-code": _export_claude_code,
    "codex": _export_unverified,
    "opencode": _export_unverified,
}


def session_export(native_path, harness="claude-code"):
    """Export a native session file. Returns a list of records with a `.dropped` Counter."""
    try:
        adapter = ADAPTERS[harness]
    except KeyError:
        raise UnsupportedFormatError(f"unknown harness {harness!r}: {UNSUPPORTED}") from None
    return adapter(native_path)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or len(argv) > 3:
        print("usage: session_export.py <native.jsonl> <out.jsonl> [harness]", file=sys.stderr)
        return 2
    try:
        records = session_export(argv[0], *argv[2:])
        write_records(records, Path(argv[1]))
    except (UnsupportedFormatError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for reason, count in sorted(records.dropped.items()):
        print(f"dropped {reason}: {count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
