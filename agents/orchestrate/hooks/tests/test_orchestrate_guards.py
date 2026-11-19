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
    def call(self, tmp, prompt="check", reason="", session="s1", delay=1200):
        return run("schedule-wakeup-guard", {"tool_name": "ScheduleWakeup", "session_id": session,
                   "tool_input": {"prompt": prompt, "reason": reason, "delaySeconds": delay}}, tmp=tmp)

    def test_first_wake_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(decision(self.call(tmp)))

    def test_same_prompt_repeated_is_denied_on_the_third(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = [decision(self.call(tmp, prompt="<<autonomous-loop-dynamic>>")) for _ in range(3)]
            self.assertEqual(got, [None, None, "deny"])

    def test_different_prompts_do_not_add_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([decision(self.call(tmp, prompt=f"p{i}")) for i in range(4)], [None] * 4)

    def test_pr_or_subagent_wait_is_denied_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            for reason in ("re-check gh pr view 277", "wait for the subagent", "gh issue list again"):
                with self.subTest(reason=reason):
                    r = self.call(tmp, reason=reason, prompt=reason)
                    self.assertEqual(decision(r), "deny")
                    self.assertIn("Monitor", json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_sessions_are_counted_apart_and_ids_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(2):
                self.call(tmp, prompt="x", session="a")
            self.assertIsNone(decision(self.call(tmp, prompt="x", session="b")))
            self.call(tmp, session="../../evil")
            self.assertFalse(os.path.exists(os.path.join(tmp, "..", "..", "evil")))

    def test_reason_names_no_private_tooling(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.call(tmp, reason="gh pr view 1", prompt="x")
            reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
            for word in ("swarm-status", "babysit"):
                self.assertNotIn(word, reason)

    def test_state_file_uses_agent_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.call(tmp, session="pfx")
            self.assertEqual(os.listdir(tmp), ["agent-schedule-wakeup-guard.pfx"])

    def test_empty_tmpdir_falls_back_to_tmp(self):
        # an empty TMPDIR must not turn the state path into a relative one
        with tempfile.TemporaryDirectory() as cwd:
            env = {**os.environ, "TMPDIR": ""}
            subprocess.run([sys.executable, os.path.join(HOOKS, "schedule-wakeup-guard")],
                           input=json.dumps({"tool_name": "ScheduleWakeup", "session_id": "emptytmp",
                                             "tool_input": {"prompt": "p"}}),
                           capture_output=True, text=True, timeout=20, env=env, cwd=cwd)
            self.assertEqual(os.listdir(cwd), [])
        os.unlink("/tmp/agent-schedule-wakeup-guard.emptytmp")

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
