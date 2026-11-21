"""Shared helpers for the reflect scripts. Standard library only, no network.

The functions here are harness-neutral where they can be: turn classes, hook
outcomes, secret scrubbing and time handling. Everything that depends on how
Claude Code lays out a transcript sits in the ADAPTER section at the end of the
file (see references/adapter-claude-code.md). Another harness gets its own
adapter that yields the same entry shape.
"""
import datetime as dt
import json
import math
import os
import re

# --- time ---------------------------------------------------------------------


def parse_ts(value):
    """Epoch seconds of an ISO timestamp (date-only or full, trailing Z allowed), else None."""
    if not isinstance(value, str) or not value:
        return None
    s = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def iso(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_week(epoch):
    y, w, _ = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def in_window(epoch, since, until):
    """since/until are epoch seconds or None. An undated event is in when no window is set."""
    if since is None and until is None:
        return True
    if epoch is None:
        return False
    return (since is None or epoch >= since) and (until is None or epoch <= until)


# --- turn classes (RF-06) -----------------------------------------------------

INJECTED_RE = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|"
    r"local-command-stdout|task-notification|agent-message|"
    r"cross-session-message|teammate-message)(\s[^>]*)?>"
)
PEER_RE = re.compile(r"<(cross-session-message|teammate-message|agent-message)\b")
SLASH_RE = re.compile(r"<(command-name|command-message|command-args)\b")
COMPACTION_PREFIX = "This session is being continued from a previous conversation"
SKILL_BODY_PREFIX = "Base directory for this skill"


def text_of(content):
    """Flatten a message.content (str or list of blocks) to searchable text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if isinstance(b.get("text"), str):
                out.append(b["text"])
            c = b.get("content")
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, list):
                out.append(text_of(c))
        return " ".join(out)
    return ""


def is_tool_result(content):
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def classify_user_turn(entry):
    """What a user-side entry really is. Only "human" is the person typing a new turn.

    Others: tool_result, skill_body, compaction_summary, peer, task_notification,
    slash_command, queued (typed while the agent worked; not a wait), injected
    (any other harness text), other (an attachment that is not a prompt).
    """
    if entry.get("type") == "attachment":
        att = entry.get("attachment")
        if isinstance(att, dict) and att.get("type") == "queued_command" \
                and isinstance(att.get("prompt"), str):
            return "peer" if PEER_RE.search(att["prompt"]) else "queued"
        return "other"
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if is_tool_result(content):
        return "tool_result"
    text = text_of(content)
    origin = entry.get("origin") if isinstance(entry.get("origin"), dict) else {}
    if entry.get("isCompactSummary") or text.lstrip().startswith(COMPACTION_PREFIX):
        return "compaction_summary"
    if text.lstrip().startswith(SKILL_BODY_PREFIX) or (
            entry.get("isMeta") and entry.get("sourceToolUseID")):
        return "skill_body"
    if PEER_RE.search(text) or origin.get("kind") == "peer":
        return "peer"
    if "<task-notification>" in text:
        return "task_notification"
    if SLASH_RE.search(text):
        return "slash_command"
    if entry.get("isMeta") or INJECTED_RE.search(text):
        return "injected"
    return "human"


# --- hook outcomes (RF-05) ----------------------------------------------------


def classify_hook_event(att):
    """deny, nonblocking or context for one hook event, else None (a quiet success)."""
    kind = att.get("type") if isinstance(att, dict) else None
    if not isinstance(kind, str) or not kind.startswith("hook_"):
        return None
    code = att.get("exitCode")
    decision = str(att.get("decision") or att.get("permissionDecision") or "").lower()
    if kind == "hook_blocking_error" or code == 2 or decision in ("block", "deny"):
        return "deny"
    if kind == "hook_non_blocking_error" or (isinstance(code, int) and code != 0):
        return "nonblocking"
    if kind == "hook_additional_context" or att.get("content"):
        return "context"
    return None


def flag_blocking_claims(hooks, claims):
    """Hooks someone says block, whose events were all non-blocking."""
    out = []
    for name in claims:
        h = hooks.get(name)
        if h and h.get("deny", 0) == 0 and h.get("nonblocking", 0) > 0:
            out.append(name)
    return out


# --- secret scrubbing (RF-08) --------------------------------------------------

_KEYWORDS = (r"(?:password|passwd|pwd|passphrase|secret|token|api[_-]?key|access[_-]?key|"
             r"private[_-]?key|credential)")
SCRUB_PATTERNS = (
    ("private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("api-key", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35})")),
    ("jwt", re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}")),
)
BEARER_RE = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{8,}")
ASSIGN_RE = re.compile(
    rf"(?i)(\b[\w.-]*{_KEYWORDS}s?[\w.-]*\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)")
LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-+/=.]{32,}")
GIT_HASH_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ENTROPY_MIN = 4.0
SECRET_CMD_RE = re.compile(
    r"\b(?:cat|less|more|head|tail|bat|echo|printf|printenv|env)\b[^|;&\n]*"
    r"(?:token|secret|password|passwd|credential|\.env\b|id_rsa|id_ed25519|\.netrc|"
    r"api[_-]?key|\.pem\b)"
    r"|security\s+find-(?:generic|internet)-password"
    r"|\b(?:op\s+(?:read|item\s+get)|pass\s+show|gopass\s+show|bw\s+get|vault\s+kv\s+get)\b"
    r"|\bgpg\s+(?:-d|--decrypt)\b|^\s*(?:printenv|env)\s*$", re.I)


def _entropy(s):
    counts = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def _long_token(m):
    tok = m.group(0)
    if "/" in tok and "=" not in tok:  # path-shaped: a worktree path, not a secret
        return tok
    if GIT_HASH_RE.match(tok):
        return tok
    if re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok) and _entropy(tok) >= ENTROPY_MIN:
        return "[redacted:token]"
    return tok


def scrub(text):
    """Redact secrets in text. Idempotent; never raises on odd input."""
    if not isinstance(text, str):
        return text
    for kind, rx in SCRUB_PATTERNS:
        text = rx.sub(f"[redacted:{kind}]", text)
    text = BEARER_RE.sub(r"\1[redacted:bearer]", text)
    text = ASSIGN_RE.sub(r"\1[redacted:value]", text)
    return LONG_TOKEN_RE.sub(_long_token, text)


def scrub_result(command, text):
    """Scrub a tool result; drop it whole when its command prints secrets."""
    if isinstance(command, str) and SECRET_CMD_RE.search(command):
        return "[redacted: output of a secret-printing command]"
    return scrub(text)


# --- ADAPTER: Claude Code transcripts (see references/adapter-claude-code.md) ---


def iter_entries(path):
    """Yield (line number, entry dict) for each JSON object line of a transcript."""
    with open(path, errors="replace") as fh:
        for ln, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                o = json.loads(raw)
            except ValueError:
                continue
            if isinstance(o, dict):
                yield ln, o


def entry_time(entry):
    """Event time (epoch seconds) from the entry's own `timestamp` field, else None."""
    return parse_ts(entry.get("timestamp"))


def message_of(entry):
    msg = entry.get("message")
    return msg if isinstance(msg, dict) else {}


COST_STATE_KEYS = ("totalCostUsd", "totalCostUSD")  # the spelling differs between versions


def cost_state(entry):
    """(running session cost, harness flagged an unpriced model) for an entry that carries the
    harness's own cost, else None. Claude Code logs it on `cost-state` entries. A transcript
    without them never yields one, so cost.py falls back to per-message usage."""
    if entry.get("type") != "cost-state":
        return None
    value = next((entry[k] for k in COST_STATE_KEYS if isinstance(entry.get(k), (int, float))), None)
    return None if value is None else (value, bool(entry.get("hasUnknownModelCost")))


def collect_files(paths):
    """Every .jsonl under the given files and folders, sorted and unique."""
    import glob
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.jsonl"), recursive=True)
        elif p.endswith(".jsonl"):
            files.append(p)
    return sorted(set(files))


# Names below are how Claude Code spells things the metrics need; another adapter
# redefines them. The core scripts only call these.
TIMER_TOOLS = ("ScheduleWakeup", "Monitor", "ListAgents")  # a call whose result wakes the agent
SKILL_TOOL = "Skill"
INTERRUPT_PREFIX = "[Request interrupted by user"
DENIAL_MARKERS = ("The user doesn't want to proceed with this tool use", "Permission to use")
HOOK_TEXT_FIELDS = ("stderr", "content", "stdout", "output", "text")


def hook_text(att):
    """The message a hook event carried (first non-empty field), else an empty string."""
    for field in HOOK_TEXT_FIELDS:
        v = att.get(field) if isinstance(att, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# A hook that denies through JSON `permissionDecision` leaves no attachment, only a tool result
# that starts `<Event>:<Tool> hook error: <reason>`. Anchored: the same words inside other output
# (a file dump, a quoted log) are not a denial.
HOOK_DENIAL_RE = re.compile(r"\A\s*(\w+(?::[\w.\-]+)+) hook error: ?(.*)", re.S)
HOOK_REASON_MAX = 80


def tool_result_hook_denial(text):
    """(hook name, reason cut to 80 chars and scrubbed) for a tool result that reports a hook
    denial, else None. The hook name matches `hookName` on the hook's own attachments."""
    m = HOOK_DENIAL_RE.match(text) if isinstance(text, str) else None
    if not m:
        return None
    reason = re.sub(r"\s+", " ", scrub(m.group(2)[:HOOK_REASON_MAX * 3])).strip()
    return m.group(1), reason[:HOOK_REASON_MAX]


def pr_ref(entry):
    """`owner/repo#number` of a pr-link entry, else None. Repeats are the caller's to dedupe."""
    if entry.get("type") != "pr-link":
        return None
    repo, num = entry.get("prRepository"), entry.get("prNumber")
    if isinstance(repo, str) and repo and isinstance(num, int):
        return f"{repo}#{num}"
    return None


def session_id_of(entry):
    sid = entry.get("sessionId")
    return sid if isinstance(sid, str) and sid else None


def cwd_of(entry):
    cwd = entry.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else None
