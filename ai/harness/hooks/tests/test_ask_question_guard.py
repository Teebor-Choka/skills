"""Tests for hooks/ask-question-guard.py. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ask-question-guard.py")


def run(payload=None, raw=None):
    return subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
                          capture_output=True, text=True, timeout=20)


def decision(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout else None


class AskQuestionGuard(unittest.TestCase):
    def call(self, tool_input, name="AskUserQuestion"):
        return run({"tool_name": name, "tool_input": tool_input})

    def test_empty_or_missing_questions_denied(self):
        for ti in ({"questions": []}, {}, {"questions": None}, {"questions": "x"}):
            with self.subTest(ti=ti):
                r = self.call(ti)
                self.assertEqual(decision(r), "deny")
                self.assertIn("Monitor", json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_real_question_passes(self):
        self.assertIsNone(decision(self.call({"questions": [{"question": "a?"}]})))

    def test_other_tool_and_junk_fail_open(self):
        self.assertIsNone(decision(self.call({"questions": []}, name="Bash")))
        for raw in ("", "not json", "[]", "null"):
            self.assertEqual(run(raw=raw).returncode, 0)


if __name__ == "__main__":
    unittest.main()
