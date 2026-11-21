"""Tests for hooks/git-index (SessionStart). Run: python3 -m pytest hooks/tests"""
import json
import os
import time
import unittest

from cg_support import Sandbox, git

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "git-index")


def context(result):
    return json.loads(result.stdout)["hookSpecificOutput"]


class GitIndex(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def test_indexes_repo_in_background_and_names_the_project(self):
        r = self.sb.run(HOOK, {"session_id": "s", "cwd": self.sb.repo})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = context(r)
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn(self.sb.project, out["additionalContext"])
        self.assertIn("search_graph", out["additionalContext"])
        self.sb.calls_seen(wait=5)
        time.sleep(1.0)  # long enough for a stray second call to land
        calls = self.sb.calls_seen()
        self.assertEqual(len(calls), 1)
        self.assertIn("index_repository", calls[0])
        self.assertIn(self.sb.repo, calls[0])

    def test_payload_cwd_wins_over_project_dir_env(self):
        r = self.sb.run(HOOK, {"cwd": self.sb.repo}, CLAUDE_PROJECT_DIR="/nonexistent")
        self.assertIn(self.sb.project, context(r)["additionalContext"])

    def test_falls_back_to_project_dir_env_without_cwd(self):
        r = self.sb.run(HOOK, {"session_id": "s"}, CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertIn(self.sb.project, context(r)["additionalContext"])

    def test_linked_worktree_indexes_main_checkout_and_says_so(self):
        wt = os.path.join(self.sb.tmp, "wt")
        git("worktree", "add", "-q", "-b", "feat", wt, cwd=self.sb.repo)
        r = self.sb.run(HOOK, {"cwd": wt})
        ctx = context(r)["additionalContext"]
        self.assertIn("linked worktree", ctx)
        self.assertIn(self.sb.project, ctx)
        self.assertIn(self.sb.repo, self.sb.calls_seen(wait=5)[0])

    def test_silent_outside_a_git_repo(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        r = self.sb.run(HOOK, {"cwd": plain})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.sb.calls_seen(), [])

    def test_silent_without_the_graph_binary(self):
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        r = sb.run(HOOK, {"cwd": sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_empty_payload_does_not_break(self):
        r = self.sb.run(HOOK, "{}", CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
