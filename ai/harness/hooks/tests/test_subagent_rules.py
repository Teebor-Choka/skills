"""Tests for hooks/subagent-rules.py (SubagentStart). Run: python3 -m unittest discover -s hooks/tests"""
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "subagent-rules.py")


def run(raw="{}"):
    r = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]


class SubagentRules(unittest.TestCase):
    def test_output_is_valid_subagentstart_json(self):
        self.assertEqual(run()["hookEventName"], "SubagentStart")

    def test_keeps_the_concision_rule(self):
        self.assertIn("no em-dashes", run()["additionalContext"])

    def test_teaches_the_wait_rules(self):
        ctx = run()["additionalContext"]
        self.assertIn("foreground `sleep`", ctx)
        self.assertIn("5 s or less is fine", ctx)  # the hook allows a short settle pause
        self.assertIn("run_in_background", ctx)
        self.assertIn("ToolSearch select:Monitor", ctx)  # Monitor is deferred: load it first
        self.assertIn("gh pr checks", ctx)  # no polling of PR state

    def test_teaches_the_worktree_command_rules(self):
        ctx = run()["additionalContext"]
        self.assertIn("one plain command per Bash call", ctx)
        self.assertIn("git -C", ctx)
        self.assertIn("script file", ctx)

    def test_bad_stdin_still_injects_the_rules(self):
        for raw in ("", "not json", "[]"):
            with self.subTest(raw=raw):
                self.assertIn("no em-dashes", run(raw)["additionalContext"])


if __name__ == "__main__":
    unittest.main()
