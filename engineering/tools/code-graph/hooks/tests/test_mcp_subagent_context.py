"""Tests for hooks/mcp-subagent-context (SubagentStart): only the code-graph directive lives here.
Run: python3 -m pytest hooks/tests"""
import json
import os
import unittest

from cg_support import Sandbox

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp-subagent-context")


class SubagentContext(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def ctx(self, payload, **env):
        r = self.sb.run(HOOK, payload, **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout else None

    def test_emits_the_graph_directive_for_an_indexed_repo(self):
        out = self.ctx({"cwd": self.sb.repo})
        self.assertEqual(out["hookEventName"], "SubagentStart")
        text = out["additionalContext"]
        self.assertIn(self.sb.project, text)
        self.assertIn("search_graph", text)

    def test_carries_no_voice_wait_or_worktree_rules(self):
        text = self.ctx({"cwd": self.sb.repo})["additionalContext"]
        for word in ("em-dash", "concisely", "sleep", "Monitor", "run_in_background", "worktree", "gh pr"):
            self.assertNotIn(word, text)

    def test_payload_cwd_wins_over_project_dir_env(self):
        out = self.ctx({"cwd": self.sb.repo}, CLAUDE_PROJECT_DIR="/nonexistent")
        self.assertIn(self.sb.project, out["additionalContext"])

    def test_falls_back_to_project_dir_env_without_cwd(self):
        out = self.ctx({}, CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertIn(self.sb.project, out["additionalContext"])

    def test_silent_outside_a_repo(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        self.assertIsNone(self.ctx({"cwd": plain}))

    def test_silent_without_the_graph_binary(self):
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        r = sb.run(HOOK, {"cwd": sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
