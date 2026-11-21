#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge a handoff note (then keep working) when the context grows large.

Spend per turn rises with context size, not with session age. The hook reads the transcript, takes the context size of the latest main-thread usage
block (input + cache creation + cache read tokens) and counts compact_boundary entries. It injects
additionalContext once per trigger: at 700K, at 800K, and at the second compaction. Wall-clock age is
never used. A jump past both thresholds fires the 800K message only. Per-session state lives in a small
JSON file in $TMPDIR (or /tmp when unset or empty), keyed by the sanitised session id: the nudges already
sent, the compactions counted so far, and the transcript byte offset scanned so far, so each prompt reads
only the new lines. A transcript smaller than the saved offset was replaced and is scanned afresh. Fails open
and silent on malformed input or an unreadable transcript.

The transcript parser is Claude Code's: JSONL with `type=assistant`, `message.usage` and
`subtype=compact_boundary` entries. A transcript in any other shape yields no context size and no
compaction count, so the hook stays silent rather than guess.

Tests: hooks/tests/test_context_reset_nudge.py.
"""
import json
import os
import re
import sys

LEVELS = [  # (state key, token threshold), highest first
    ("800k", 800_000),
    ("700k", 700_000),
]
COMPACTION_LIMIT = 2
TAIL_BYTES = 2_000_000

HANDOFF = ("write a handoff file of at most 15 lines (goal, state, decisions, next steps, open PRs and "
           "branches, file paths) next to the work and tell the user its path. Then keep working: do not stop "
           "or ask for a fresh session, autocompact takes over once the file exists.")
MESSAGES = {
    "700k": "Context is past 700K tokens. Finish the current unit, then " + HANDOFF,
    "800k": "Context is past 800K tokens: " + HANDOFF,
    "compact2": "This session has compacted twice, and live state is lost at each compaction. Now " + HANDOFF,
}


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value)).lstrip(".") or "nosession"


def latest_context(path):
    """Context tokens of the newest main-thread assistant usage block, or None.

    Claude transcript shape only; any other shape finds no usage block and returns None (fail open)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        tail = f.read().decode("utf-8", "replace")
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("type") != "assistant" or entry.get("isSidechain"):
                continue
            usage = entry["message"]["usage"]
            total = sum(int(usage.get(k) or 0) for k in
                        ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if total > 0:
            return total
    return None


def scan_compactions(path, offset):
    """(new compact_boundary entries after `offset`, new offset). Streams complete lines only: a partial last
    line is left for the next run. An entry counts only when its JSON is a system entry with that subtype, so
    the words quoted inside a message never count. A file smaller than `offset` was replaced: the caller
    resets."""
    count = 0
    with open(path, "rb") as f:
        f.seek(offset)
        while True:
            line = f.readline()
            if not line.endswith(b"\n"):
                return count, offset  # end of file, or a line still being written
            offset += len(line)
            if b"compact_boundary" not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
                count += 1


def open_state(path, write):
    """Open a state file without following a symlink planted in a shared temp dir; private when created."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC if write else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(path, flags, 0o600), "w" if write else "r")


def load_state(path):
    """{"done": set of nudge keys, "offset": scanned bytes, "compactions": count}. The first release stored
    a bare list of keys; it is still read (offset 0 rescans the transcript once)."""
    state = {"done": set(), "offset": 0, "compactions": 0}
    try:
        with open_state(path, False) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return state
    if isinstance(data, list):
        state["done"] = {k for k in data if isinstance(k, str)}
    elif isinstance(data, dict):
        state["done"] = {k for k in data.get("done", []) if isinstance(k, str)} if isinstance(data.get("done"), list) else set()
        for key in ("offset", "compactions"):
            if isinstance(data.get(key), int) and not isinstance(data.get(key), bool) and data[key] >= 0:
                state[key] = data[key]
    return state


def save_state(path, state):
    try:
        with open_state(path, True) as f:
            json.dump({"done": sorted(state["done"]), "offset": state["offset"],
                       "compactions": state["compactions"]}, f)
        return True
    except OSError:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
        session, transcript = payload.get("session_id"), payload.get("transcript_path")
        if not isinstance(session, str) or not isinstance(transcript, str):
            return
        state_path = os.path.join(os.environ.get("TMPDIR") or "/tmp", "agent-context-reset-nudge." + safe(session))
        state = load_state(state_path)
        context = latest_context(transcript)
        if os.path.getsize(transcript) < state["offset"]:
            state.update(offset=0, compactions=0)  # the transcript was replaced: scan it afresh
        added, offset = scan_compactions(transcript, state["offset"])
    except Exception:
        return

    changed = offset != state["offset"]
    state.update(offset=offset, compactions=state["compactions"] + added)
    now = [key for key, limit in LEVELS if context is not None and context >= limit][:1]
    if state["compactions"] >= COMPACTION_LIMIT:
        now.append("compact2")
    done = set(state["done"])
    if "800k" in done:
        done.add("700k")  # the 800K message supersedes the 700K one
    todo = [k for k in now if k not in done]
    if not todo:
        if changed:
            save_state(state_path, state)  # remember the offset; a failed write only costs a rescan
        return
    state["done"] = done | set(todo) | ({"700k"} if "800k" in todo else set())
    if not save_state(state_path, state):
        return  # cannot remember what was said: stay silent rather than repeat every prompt
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": " ".join(MESSAGES[k] for k in todo)}}))


if __name__ == "__main__":
    main()
