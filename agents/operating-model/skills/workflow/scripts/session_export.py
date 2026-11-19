"""Standard session record and the Claude Code extractor (decision D22).

Every harness keeps its session in a native format. An adapter exports it to
one record format, one JSON object per line, so any run can be read and
replayed. The schema is documented in schemas/session/record.schema.json. The
loader here checks records with the standard library only.

Only the Claude Code adapter is verified. Codex and OpenCode formats are not
verified (see the format research), so their adapters refuse.
"""
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1"
HARNESS = "claude-code"
UNSUPPORTED = "unsupported format: not verified"

STR, STR_OR_NONE, INT, BOOL, OBJ = "str", "str|None", "int", "bool", "object"

COMMON = {
    "schema_version": STR, "harness": STR, "session_id": STR, "seq": INT,
    "uuid": STR, "parent_uuid": STR_OR_NONE, "timestamp": STR, "kind": STR,
}

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


# ---- redaction --------------------------------------------------------------

REDACTED = "[REDACTED]"
_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"),
]
_SECRET_KEY = re.compile(r"(?i)(secret|token|passw|api[_-]?key|authorization|credential)")


def redact(text):
    for p in _PATTERNS:
        text = p.sub(REDACTED, text)
    return text


def _redact_value(v):
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, list):
        return [_redact_value(x) for x in v]
    if isinstance(v, dict):
        return {k: REDACTED if isinstance(x, str) and _SECRET_KEY.search(k) else _redact_value(x)
                for k, x in v.items()}
    return v


# ---- validation -------------------------------------------------------------

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
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")


def write_records(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            validate_record(r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_records(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                validate_record(r)
            except ValueError as e:
                raise ValueError(f"{path}: line {n}: {e}") from e
            out.append(r)
    return out


# ---- Claude Code extractor --------------------------------------------------

def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(str(b.get("text", "")))
            elif isinstance(b, dict):
                parts.append(f"[{b.get('type', 'unknown')} omitted]")
        return "\n".join(parts)
    return "" if content is None else str(content)


def _blocks(message):
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _extract_line(obj):
    """Yield (kind, fields) for one native line. Thinking and bookkeeping lines yield nothing."""
    ty = obj.get("type")
    if ty == "system":
        yield "system", {"subtype": obj.get("subtype"), "content": str(obj.get("content", ""))}
        return
    if ty not in ("user", "assistant"):
        return
    message = obj.get("message")
    for b in _blocks(message):
        bt = b.get("type")
        if ty == "user" and bt == "text":
            kind = "compaction" if obj.get("isCompactSummary") else "user"
            yield kind, {"text": str(b.get("text", ""))}
        elif ty == "user" and bt == "tool_result":
            yield "tool_result", {
                "tool_use_id": str(b.get("tool_use_id", "")),
                "content": _result_text(b.get("content")),
                "is_error": bool(b.get("is_error", False)),
            }
        elif ty == "assistant" and bt == "text":
            model = message.get("model") if isinstance(message, dict) else None
            yield "assistant_text", {"text": str(b.get("text", "")),
                                     "model": model if isinstance(model, str) else None}
        elif ty == "assistant" and bt == "tool_use":
            inp = b.get("input")
            yield "tool_call", {"tool_use_id": str(b.get("id", "")), "name": str(b.get("name", "")),
                                "input": inp if isinstance(inp, dict) else {}}


def _export_claude_code(native_path):
    records = []
    with open(native_path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError as e:
                raise ValueError(f"{native_path}: line {n}: invalid JSON: {e}") from e
            if not isinstance(obj, dict):
                continue
            for kind, fields in _extract_line(obj):
                rec = {
                    "schema_version": SCHEMA_VERSION, "harness": HARNESS,
                    "session_id": str(obj.get("sessionId", "")), "seq": len(records),
                    "uuid": str(obj.get("uuid", "")), "parent_uuid": obj.get("parentUuid"),
                    "timestamp": str(obj.get("timestamp", "")), "kind": kind,
                    **_redact_value(fields),
                }
                validate_record(rec)
                records.append(rec)
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
    """Export a native session file to a list of standard records."""
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
        write_records(session_export(argv[0], *argv[2:]), Path(argv[1]))
    except (UnsupportedFormatError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
