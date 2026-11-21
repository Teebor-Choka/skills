"""Tests for hooks/worktree-path-guard. Run: python3 -m unittest discover -s hooks/tests -v"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worktree-path-guard")
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   cwd=cwd, env=GIT_ENV, check=True, capture_output=True, stdin=subprocess.DEVNULL)


def run_hook(payload=None, raw=None, env=None):
    return subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
                          capture_output=True, text=True, timeout=20, env=env or GIT_ENV)


def edit(cwd, path, tool="Edit"):
    return {"tool_name": tool, "cwd": cwd, "tool_input": {"file_path": path}}


class WorktreePathGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.main = os.path.realpath(os.path.join(cls.tmp.name, "repo"))
        os.makedirs(cls.main)
        git("init", "-q", "-b", "main", cwd=cls.main)
        with open(os.path.join(cls.main, "a.txt"), "w") as f:
            f.write("x")
        git("add", "a.txt", cwd=cls.main)
        git("commit", "-q", "-m", "i", cwd=cls.main)
        cls.wt = os.path.join(cls.main, ".claude", "worktrees", "w1")  # in-repo worktree
        git("worktree", "add", "-q", "-b", "w1", cls.wt, cwd=cls.main)
        cls.wt2 = os.path.join(cls.tmp.name, "sibling-wt")  # worktree outside the repo dir
        git("worktree", "add", "-q", "-b", "w2", cls.wt2, cwd=cls.main)
        cls.other = os.path.join(cls.main, ".claude", "worktrees", "w3")
        git("worktree", "add", "-q", "-b", "w3", cls.other, cwd=cls.main)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assert_silent(self, r):
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def assert_denied_with(self, r, expected):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn(expected, out["permissionDecisionReason"])

    def test_main_checkout_path_from_worktree_denied_with_equivalent(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assert_denied_with(run_hook(edit(self.wt, f"{self.main}/src/a.rs", tool)),
                                        f"{self.wt}/src/a.rs")

    def test_sibling_worktree_outside_repo_dir(self):
        self.assert_denied_with(run_hook(edit(self.wt2, f"{self.main}/a.txt")), f"{self.wt2}/a.txt")

    def test_cwd_in_worktree_subdir(self):
        os.makedirs(os.path.join(self.wt, "sub"), exist_ok=True)
        self.assert_denied_with(run_hook(edit(os.path.join(self.wt, "sub"), f"{self.main}/a.txt")),
                                f"{self.wt}/a.txt")

    def test_path_inside_worktree_allowed(self):
        self.assert_silent(run_hook(edit(self.wt, f"{self.wt}/a.txt")))

    def test_other_worktree_path_allowed(self):
        self.assert_silent(run_hook(edit(self.wt, f"{self.other}/a.txt")))

    def test_unrelated_path_allowed(self):
        self.assert_silent(run_hook(edit(self.wt, "/etc/hosts")))
        self.assert_silent(run_hook(edit(self.wt, f"{self.main}-other/a.txt")))  # sibling prefix, not the repo

    def test_cwd_in_main_checkout_allowed(self):
        self.assert_silent(run_hook(edit(self.main, f"{self.main}/a.txt")))

    def test_non_git_cwd_allowed(self):
        self.assert_silent(run_hook(edit(self.tmp.name, f"{self.main}/a.txt")))

    def test_path_pattern_without_git(self):
        # git cannot answer (empty PATH, nonexistent dirs): the .claude/worktrees/ layout still identifies the pair.
        env = {**GIT_ENV, "PATH": ""}
        r = run_hook(edit("/nonexistent/proj/.claude/worktrees/w", "/nonexistent/proj/src/a.rs"), env=env)
        self.assert_denied_with(r, "/nonexistent/proj/.claude/worktrees/w/src/a.rs")
        r = run_hook(edit("/nonexistent/proj/.agents/worktrees/w", "/nonexistent/proj/src/a.rs"), env=env)
        self.assert_denied_with(r, "/nonexistent/proj/.agents/worktrees/w/src/a.rs")

    def test_git_unavailable_plain_dir_fails_open(self):
        self.assert_silent(run_hook(edit("/nonexistent/proj", "/nonexistent/proj/a.rs"), env={**GIT_ENV, "PATH": ""}))

    def test_other_tool_and_malformed_input_fail_open(self):
        self.assert_silent(run_hook({"tool_name": "Read", "cwd": self.wt, "tool_input": {"file_path": f"{self.main}/a"}}))
        self.assert_silent(run_hook({"tool_name": "Edit", "cwd": self.wt, "tool_input": {}}))
        self.assert_silent(run_hook({"tool_name": "Edit", "tool_input": {"file_path": f"{self.main}/a"}}))
        self.assert_silent(run_hook(edit(self.wt, "relative/a.rs")))
        for raw in ("", "not json", "[]", '{"tool_name":"Edit"}'):
            with self.subTest(raw=raw):
                self.assert_silent(run_hook(raw=raw))


if __name__ == "__main__":
    unittest.main()
