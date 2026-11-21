#!/usr/bin/env python3
"""PreToolUse hook (ask.user): deny a call with no questions.

An empty `questions` array fails schema validation and was followed by an empty reply. The agent used
the dialog to pause or wait for CI. Fails open on malformed input.
Tests: hooks/tests/test_ask_question_guard.py.
"""
import json
import sys

REASON = "Nothing to ask. To wait, use Monitor (load it with ToolSearch select:Monitor); to stop, end the turn."


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("tool_name") != "AskUserQuestion":
            return
        questions = (payload.get("tool_input") or {}).get("questions")
    except Exception:
        return
    if isinstance(questions, list) and questions:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": REASON}}))


if __name__ == "__main__":
    main()
