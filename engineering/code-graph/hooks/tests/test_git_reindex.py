"""Tests for hooks/git-reindex (Stop). Run: python3 -m pytest hooks/tests"""
import os
import unittest

from cg_support import Sandbox, git

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "git-reindex")


class GitReindex(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def dirty(self):
        with open(os.path.join(self.sb.repo, "a.txt"), "w") as f:
            f.write("x")

    def test_dirty_tree_triggers_one_background_index(self):
        self.dirty()
        r = self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        calls = self.sb.calls_seen(wait=5)
        self.assertEqual(len(calls), 1)
        self.assertIn("index_repository", calls[0])
        self.assertIn(self.sb.repo, calls[0])

    def test_clean_tree_does_nothing(self):
        r = self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.sb.calls_seen(wait=0.5), [])

    def test_held_lock_skips_the_refresh(self):
        self.dirty()
        os.makedirs(os.path.join(self.sb.home, ".cache"))
        lock = os.path.join(self.sb.home, ".cache", "git-reindex." + self.sb.repo.replace("/", "_") + ".lock")
        os.makedirs(lock)
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual(self.sb.calls_seen(wait=0.5), [])

    def test_lock_is_released_after_the_index_finishes(self):
        self.dirty()
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.sb.calls_seen(wait=5)
        lock = os.path.join(self.sb.home, ".cache", "git-reindex." + self.sb.repo.replace("/", "_") + ".lock")
        for _ in range(50):
            if not os.path.exists(lock):
                break
            import time
            time.sleep(0.1)
        self.assertFalse(os.path.exists(lock))

    def test_payload_cwd_wins_over_project_dir_env(self):
        self.dirty()
        self.sb.run(HOOK, {"cwd": self.sb.repo}, CLAUDE_PROJECT_DIR="/nonexistent")
        self.assertEqual(len(self.sb.calls_seen(wait=5)), 1)

    def test_falls_back_to_project_dir_env_without_cwd(self):
        self.dirty()
        self.sb.run(HOOK, {}, CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertEqual(len(self.sb.calls_seen(wait=5)), 1)

    def test_linked_worktree_edits_leave_the_main_checkout_clean(self):
        wt = os.path.join(self.sb.tmp, "wt")
        git("worktree", "add", "-q", "-b", "feat", wt, cwd=self.sb.repo)
        with open(os.path.join(wt, "b.txt"), "w") as f:
            f.write("x")
        self.sb.run(HOOK, {"cwd": wt})
        self.assertEqual(self.sb.calls_seen(wait=0.5), [])

    def test_silent_outside_a_repo_and_without_binary(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(self.sb.run(HOOK, {"cwd": plain}).returncode, 0)
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        with open(os.path.join(sb.repo, "a.txt"), "w") as f:
            f.write("x")
        r = sb.run(HOOK, {"cwd": sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(sb.calls_seen(wait=0.3), [])


if __name__ == "__main__":
    unittest.main()
