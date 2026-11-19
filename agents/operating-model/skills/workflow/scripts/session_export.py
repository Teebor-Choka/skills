"""Standard session record and the Claude Code extractor (decision D22).

Every harness keeps its session in a native format. An adapter exports it to
one record format, one JSON object per line, so any run can be read and
replayed. The schema is documented in schemas/session/record.schema.json. The
loader here checks records with the standard library only.

Only the Claude Code adapter is verified. Codex and OpenCode formats are not
verified (see the format research), so their adapters refuse.

Nothing is dropped or changed silently. session_export returns a list that
carries three tallies, and the CLI prints them to stderr:
- `dropped`: Counter of items left out, by reason.
- `redactions`: number of strings or values replaced by "[REDACTED]".
- `altered`: Counter of other changes: null_to_empty_string, model_not_string,
  tool_input_null_to_empty_object, tool_input_wrapped_as_raw (a non-object
  tool input becomes {"_raw": text}) and key_collision_suffix (two redacted
  dict keys got the same name, so one gets a "_" suffix).

Changes that are intended and not counted one by one:
- Redaction is pattern based and over-redacts on purpose. A key that looks
  secret (for example max_tokens, matched by "token") has its value of any
  type replaced by the string "[REDACTED]", so the type can change. Each
  replacement is counted in `redactions`.
- An unquoted value after ":" is redacted to the end of the line. After "="
  it ends at whitespace, as a shell word does. An Authorization or Cookie
  value always runs to the end of the line.
- A tool result with several text parts is joined with a newline. A part that
  is not text becomes "[<type> omitted]" and is counted as tool_result_non_text.
- Native fields outside the record schema are not exported (cwd, version,
  gitBranch, userType, level, attachments, and every field of an unknown line
  except its type name). A missing isSidechain, isMeta or is_error means false.
  Any other non-boolean value raises with the line number.
- Numbers must be finite: NaN, Infinity and values such as 1e999 raise.

`(uuid, block_index)` is the record key, because one native line can hold
several blocks.
"""
import json
import math
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
    """The exported records, plus the tallies `dropped`, `redactions` and `altered`."""

    def __init__(self, *a):
        super().__init__(*a)
        self.dropped = Counter()
        self.altered = Counter()
        self.redactions = 0


# ---- redaction --------------------------------------------------------------

REDACTED = "[REDACTED]"
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")
# Userinfo runs to the LAST "@" before the first "/" or whitespace, so a raw "@", "#" or "?" in
# the password cannot end it early. The username may be empty (redis://:pw@host).
_URL_CREDS = re.compile(r"(?i)(?<![a-z0-9+.-])([a-z][a-z0-9+.-]*://)[^/?#\s:@]*:[^/\s]+@")
_TOKENS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),
    re.compile(r"/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
]
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_KEY = re.compile(
    r"(?i)passw|passphrase|secret|token|api[_-]?key|private[_-]?key|credential"
    r"|signing[_-]?key|access[_-]?key|encryption[_-]?key|master[_-]?key|authorization|cookie"
    r"|(?<![a-z0-9])(?:pwd|auth)(?![a-z0-9])")
# One word run (the possible key), an optional closing quote, then "=>", "=" or ":". The run is
# matched once and tested in code, so a long run costs linear time.
_KEY = re.compile(r"(?<![\w.-])([\w.-]+)(?:\\*[\"'])?\s*(=>|[=:])\s*")
_LINE_END = re.compile(r"[^\r\n]*")
_WORD = re.compile(r"[^\s]+")
_QUERY_WORD = re.compile(r"[^\s&#\"']+")


def _quoted_end(text, i):
    """Return (opener, end) for a quoted value that starts at text[i], or None.

    The opener is backslashes plus a quote char (a shell-escaped or double-encoded JSON quote).
    `end` is the index just after the closing quote, or len(text) when it is missing.
    """
    j = i
    while j < len(text) and text[j] == "\\":
        j += 1
    if j >= len(text) or text[j] not in "\"'":
        return None
    opener = text[i:j + 1]
    if j == i:  # plain quote: a backslash escapes the next char
        q, k = text[j], j + 1
        while k < len(text):
            if text[k] == "\\":
                k += 2
            elif text[k] == q:
                return opener, k + 1
            else:
                k += 1
        return opener, len(text)
    k = text.find(opener, j + 1)
    return opener, (len(text) if k == -1 else k + len(opener))


def _secret_key_at(text, m):
    key = m.group(1)
    if _SECRET_KEY.search(key):
        return True
    start = m.start(1)
    return key.lower() in ("key", "apikey") and start > 0 and text[start - 1] in "?&"


def _redact_kv(text):
    """Redact the value after every secret-looking key. Return (text, count). Linear."""
    out, pos, count = [], 0, 0
    while True:
        m = _KEY.search(text, pos)
        if not m:
            break
        if not _secret_key_at(text, m):
            # Keep scanning right after the separator; a secret key may sit inside the value.
            out.append(text[pos:m.end()])
            pos = m.end()
            continue
        vstart = m.end()
        sep, key = m.group(2), m.group(1).lower()
        quoted = _quoted_end(text, vstart)
        if quoted:
            opener, vend = quoted
            closed = vend > vstart + len(opener) and text.endswith(opener, vstart, vend)
            body_end = vend - len(opener) if closed else vend
            body = text[vstart + len(opener):body_end]
            tail = opener if closed else ""
            new = opener + REDACTED + tail
            same = body == REDACTED
        else:
            query = vstart > 0 and m.start(1) > 0 and text[m.start(1) - 1] in "?&"
            if query:
                vend = _QUERY_WORD.match(text, vstart).end()
            elif sep == ":" or "authorization" in key or "cookie" in key:
                vend = _LINE_END.match(text, vstart).end()
            else:
                w = _WORD.match(text, vstart)
                vend = w.end() if w else vstart
            body = text[vstart:vend]
            new = REDACTED
            same = body.strip() == REDACTED
        out.append(text[pos:vstart])
        if same or (not quoted and not body.strip()):
            out.append(text[vstart:vend])
        else:
            out.append(new)
            count += 1
        pos = vend
    out.append(text[pos:])
    return "".join(out), count


def _redact_pem(text):
    """Redact PEM and PGP private keys. An unterminated key is redacted to the end. Linear."""
    if "-----BEGIN" not in text:
        return text, 0
    parts, pos, count = [], 0, 0
    while True:
        m = _PEM_BEGIN.search(text, pos)
        if not m:
            break
        parts.append(text[pos:m.start()])
        parts.append(REDACTED)
        count += 1
        end = text.find("-----END", m.end())
        close = -1 if end == -1 else text.find("-----", end + 8)
        pos = len(text) if close == -1 else close + 5
    parts.append(text[pos:])
    return "".join(parts), count


def redact_counted(text):
    """Return (redacted text, number of replacements)."""
    total = 0
    text, n = _redact_pem(text)
    total += n
    text, n = _URL_CREDS.subn(lambda m: m.group(1) + REDACTED + "@", text)
    total += n
    text, n = _redact_kv(text)
    total += n
    for p in _TOKENS:
        text, n = p.subn(REDACTED, text)
        total += n
    text, n = _BEARER.subn(REDACTED, text)
    return text, total + n


def redact(text):
    return redact_counted(text)[0]


def _tally(tally, name, n=1):
    if tally is not None and n:
        tally[name] += n


def _redact_text(s, tally):
    out, n = redact_counted(s)
    _tally(tally, "redactions", n)
    return out


def _secret_sibling(d):
    return any(isinstance(d.get(f), str) and _SECRET_KEY.search(d[f]) for f in ("name", "key"))


def _redact_value(v, tally=None):
    """Redact every string in a JSON value. A secret-looking key redacts its value of any type.

    `tally` is an optional Counter: "redactions" and altered reasons are added to it.
    """
    if isinstance(v, str):
        return _redact_text(v, tally)
    if isinstance(v, list):
        return [_redact_value(x, tally) for x in v]
    if isinstance(v, dict):
        out = {}
        paired = _secret_sibling(v)
        for k, x in v.items():
            nk = _redact_text(k, tally) if isinstance(k, str) else k
            while nk in out:
                nk = f"{nk}_"
                _tally(tally, "key_collision_suffix")
            secret = x is not None and isinstance(k, str) and (
                _SECRET_KEY.search(k) or (paired and k == "value"))
            if secret:
                if x != REDACTED:
                    _tally(tally, "redactions")
                out[nk] = REDACTED
            else:
                out[nk] = _redact_value(x, tally)
        return out
    return v


# ---- validation and record files ---------------------------------------------

def _type_ok(value, spec):
    if spec == STR:
        return isinstance(value, str)
    if spec == STR_OR_NONE:
        return value is None or isinstance(value, str)
    if spec == INT:
        if isinstance(value, float):
            return value.is_integer()
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


def _no_constant(name):
    raise ValueError(f"non-finite number {name} is not allowed")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite number {text} is not allowed")
    return value


def _loads(text):
    try:
        return json.loads(text, parse_constant=_no_constant, parse_float=_finite_float)
    except RecursionError:
        raise ValueError("JSON nested too deeply") from None


def write_records(records, path):
    """Validate and encode everything first, then replace the file atomically."""
    chunks = []
    for r in records:
        validate_record(r)
        chunks.append((json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
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


def _flag(obj, key):
    """A native flag: missing or null is false; anything but a real boolean raises."""
    v = obj.get(key)
    if v is None:
        return False
    if not isinstance(v, bool):
        raise ValueError(f"{key} must be a boolean, got {type(v).__name__}")
    return v


def _str(v, what, altered=None):
    if v is None:
        if altered is not None:
            altered["null_to_empty_string"] += 1
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{what} must be a string, got {type(v).__name__}")
    return v


def _result_text(content, dropped, altered):
    if content is None:
        altered["null_to_empty_string"] += 1
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError(f"tool_result content must be a string or list, got {type(content).__name__}")
    parts = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(_str(b.get("text"), "tool_result text", altered))
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


def _line_records(obj, dropped, altered):
    """Return [(kind, block_index, fields)] for one native line. Count drops and alterations."""
    ty = obj.get("type")
    if ty is not None and not isinstance(ty, str):
        raise ValueError(f"type must be a string, got {type(ty).__name__}")
    if ty == "system":
        return [("system", 0, {"subtype": _opt_str(obj, "subtype"),
                               "content": _str(obj.get("content"), "system content", altered)})]
    if ty == "summary":
        return [("compaction", 0, {"text": _str(obj.get("summary"), "summary", altered)})]
    if ty in BOOKKEEPING:
        dropped["bookkeeping"] += 1
        return []
    if ty not in ("user", "assistant"):
        dropped["unknown_line"] += 1
        return [("system", 0, {"subtype": "unknown-line",
                               "content": ty if isinstance(ty, str) else ""})]
    message = obj.get("message")
    if message is not None and not isinstance(message, dict):
        dropped["non_object_message"] += 1
        return []
    blocks = _message_blocks(message)
    if not blocks:
        dropped["empty_message"] += 1
        return []
    out = []
    for i, b in blocks:
        bt = b.get("type") if isinstance(b, dict) else None
        if not isinstance(bt, str):
            bt = None
        if bt in DROPPED_BLOCKS:
            dropped[bt] += 1
        elif ty == "user" and bt == "image":
            dropped["user_image"] += 1
        elif ty == "user" and bt == "text":
            kind = "compaction" if _flag(obj, "isCompactSummary") else "user"
            out.append((kind, i, {"text": _str(b.get("text"), "text block", altered)}))
        elif ty == "user" and bt == "tool_result":
            out.append(("tool_result", i, {
                "tool_use_id": _str(b.get("tool_use_id"), "tool_use_id", altered),
                "content": _result_text(b.get("content"), dropped, altered),
                "is_error": _flag(b, "is_error"),
            }))
        elif ty == "assistant" and bt == "text":
            model = message.get("model")
            if model is not None and not isinstance(model, str):
                altered["model_not_string"] += 1
                model = None
            out.append(("assistant_text", i, {
                "text": _str(b.get("text"), "text block", altered), "model": model}))
        elif ty == "assistant" and bt == "tool_use":
            inp = b.get("input")
            if inp is None:
                altered["tool_input_null_to_empty_object"] += 1
                inp = {}
            elif not isinstance(inp, dict):
                altered["tool_input_wrapped_as_raw"] += 1
                inp = {"_raw": inp if isinstance(inp, str) else json.dumps(inp)}
            out.append(("tool_call", i, {
                "tool_use_id": _str(b.get("id"), "tool_use id", altered),
                "name": _str(b.get("name"), "tool_use name", altered), "input": inp}))
        else:
            dropped["unknown_block"] += 1
    return out


def _export_claude_code(native_path):
    records = Export()
    dropped, altered = records.dropped, records.altered
    tally = Counter()
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
                "is_sidechain": _flag(obj, "isSidechain"), "is_meta": _flag(obj, "isMeta"),
            }
            for kind, bi, fields in _line_records(obj, dropped, altered):
                rec = {"schema_version": SCHEMA_VERSION, "harness": HARNESS,
                       "seq": len(records), "kind": kind, "block_index": bi,
                       **envelope, **fields}
                rec = _redact_value(rec, tally)
                validate_record(rec)
                records.append(rec)
        except RecursionError:
            raise ValueError(f"{native_path}: line {n}: JSON nested too deeply") from None
        except ValueError as e:
            raise ValueError(f"{native_path}: line {n}: {e}") from e
    if not records:
        raise ValueError(f"{native_path}: no exportable records")
    records.redactions = tally.pop("redactions", 0)
    records.altered.update(tally)
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


def _same_file(a, b):
    try:
        if os.path.samefile(a, b):
            return True
    except OSError:
        pass
    return Path(a).resolve() == Path(b).resolve()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or len(argv) > 3:
        print("usage: session_export.py <native.jsonl> <out.jsonl> [harness]", file=sys.stderr)
        return 2
    if _same_file(argv[0], argv[1]):
        print(f"error: {argv[1]} is the same file as the input; refusing to overwrite it",
              file=sys.stderr)
        return 2
    try:
        records = session_export(argv[0], *argv[2:])
        write_records(records, Path(argv[1]))
    except (UnsupportedFormatError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for reason, count in sorted(records.dropped.items()):
        print(f"dropped {reason}: {count}", file=sys.stderr)
    for reason, count in sorted(records.altered.items()):
        print(f"altered {reason}: {count}", file=sys.stderr)
    print(f"redactions: {records.redactions}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
