#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge once to name a session that is still unnamed at its Nth prompt.

An unnamed session is hard to find and to address from a coordinator. UserPromptSubmit input carries `session_title` only when the session has a custom title (--name, /rename,
a hook's sessionTitle output); a generated title is not included, so a missing or blank field means
unnamed (https://code.claude.com/docs/en/hooks, UserPromptSubmit input). The hook counts human prompts
per session in a JSON file in $TMPDIR (or /tmp when unset or empty), keyed by the sanitised session id,
and injects additionalContext once when the count reaches NTH_PROMPT with no title. A title seen at any
prompt retires the nudge. Fails open and silent on malformed input.
Tests: hooks/tests/test_session_name_nudge.py.
"""
import json
import os
import re
import sys

NTH_PROMPT = 3
NUDGE = ("This session has no name. Suggest one to the user in the form <repo>-<issue-or-topic>-<role> "
         "(for example hooks-session-hygiene-builder) and ask them to run /rename with it, so the session "
         "can be found and addressed later. Say this once; do not ask again.")


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value)).lstrip(".") or "nosession"


def open_state(path, write):
    """Open a state file without following a symlink planted in a shared temp dir; private when created."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC if write else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(path, flags, 0o600), "w" if write else "r")


def main():
    try:
        payload = json.load(sys.stdin)
        session = payload.get("session_id")
        if not isinstance(session, str) or not session:
            return
        title = payload.get("session_title")
    except Exception:
        return
    named = isinstance(title, str) and bool(title.strip())

    path = os.path.join(os.environ.get("TMPDIR") or "/tmp", "agent-session-name-nudge." + safe(session))
    state = {}
    try:
        with open_state(path, False) as f:
            data = json.load(f)
        if isinstance(data, dict):
            state = data
    except (OSError, ValueError):
        pass
    if state.get("done"):
        return
    count = state.get("prompts", 0) if isinstance(state.get("prompts"), int) else 0
    count += 1
    fire = not named and count >= NTH_PROMPT
    state = {"prompts": count, "done": named or fire}
    try:
        with open_state(path, True) as f:
            json.dump(state, f)
    except OSError:
        return  # cannot remember: stay silent rather than nudge every prompt
    if fire:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": NUDGE}}))


if __name__ == "__main__":
    main()
