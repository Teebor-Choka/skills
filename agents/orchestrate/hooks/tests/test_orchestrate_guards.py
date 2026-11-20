"""Tests for hooks/schedule-wakeup-guard and hooks/send-message-guard. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def run(hook, payload=None, raw=None, tmp=None):
    env = {**os.environ, "TMPDIR": tmp} if tmp else None
    return subprocess.run([sys.executable, os.path.join(HOOKS, hook)],
                          input=raw if raw is not None else json.dumps(payload),
                          capture_output=True, text=True, timeout=20, env=env)


def decision(r):
    self_ok = r.returncode == 0
    assert self_ok, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout else None


class ScheduleWakeupGuard(unittest.TestCase):
    def call(self, prompt="check", reason="", session="s1", delay=1200):
        return run("schedule-wakeup-guard", {"tool_name": "ScheduleWakeup", "session_id": session,
                   "tool_input": {"prompt": prompt, "reason": reason, "delaySeconds": delay}})

    def test_first_wake_allowed(self):
        self.assertIsNone(decision(self.call()))

    def test_a_dynamic_loop_may_repeat_the_same_prompt_indefinitely(self):
        got = [decision(self.call(prompt="<<autonomous-loop-dynamic>>")) for _ in range(6)]
        self.assertEqual(got, [None] * 6)

    def test_it_keeps_no_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run("schedule-wakeup-guard", {"tool_name": "ScheduleWakeup", "session_id": "s",
                                          "tool_input": {"prompt": "p"}}, tmp=tmp)
            self.assertEqual(os.listdir(tmp), [])

    def test_polling_waits_are_denied_at_once(self):
        for reason in ("re-check gh pr view 277", "wait for the subagent", "gh issue list again",
                       "gh run list again", "sleep 300 then check", "poll the subagent"):
            with self.subTest(reason=reason):
                r = self.call(reason=reason, prompt=reason)
                self.assertEqual(decision(r), "deny")
                self.assertIn("Monitor", json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_plain_words_do_not_deny(self):
        for text in ("watch", "check back on the build", "wait", "babysit"):
            with self.subTest(text=text):
                self.assertIsNone(decision(self.call(prompt=text, reason=text)))

    def test_reason_names_no_tool_but_the_idle_reply(self):
        import re
        r = self.call(reason="gh pr view 1", prompt="x")
        reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(re.findall(r"`([^`]+)`", reason), ["idle"])

    def test_stop_and_junk_fail_open(self):
        self.assertEqual(run("schedule-wakeup-guard", {"tool_name": "ScheduleWakeup", "tool_input": {"stop": True}}).returncode, 0)
        for raw in ("", "not json", "[]"):
            self.assertEqual(run("schedule-wakeup-guard", raw=raw).returncode, 0)


class SendMessageGuard(unittest.TestCase):
    def call(self, message, to="b1"):
        return run("send-message-guard", {"tool_name": "SendMessage", "tool_input": {"to": to, "message": message}})

    def test_long_instruction_denied(self):
        r = self.call("do this and that " * 40)
        self.assertEqual(decision(r), "deny")
        self.assertIn("see #N", json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_short_message_passes(self):
        self.assertIsNone(decision(self.call("rebase onto main, then push")))

    def test_long_message_with_issue_ref_or_url_passes(self):
        self.assertIsNone(decision(self.call("see #123 " + "x" * 600)))
        self.assertIsNone(decision(self.call("https://github.com/o/r/issues/4 " + "x" * 600)))

    def test_structured_and_junk_fail_open(self):
        self.assertIsNone(decision(run("send-message-guard", {"tool_name": "SendMessage",
                                                              "tool_input": {"to": "x", "message": {"type": "shutdown_request"}}})))
        for raw in ("", "not json", "[]"):
            self.assertEqual(run("send-message-guard", raw=raw).returncode, 0)


if __name__ == "__main__":
    unittest.main()
