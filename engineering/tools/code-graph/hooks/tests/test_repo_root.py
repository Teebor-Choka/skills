"""Tests for hooks/repo-root and hooks/code-graph-index-rewrite. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REPO_ROOT = os.path.join(HOOKS, "repo-root")
REWRITE = os.path.join(HOOKS, "code-graph-index-rewrite")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def repo_root(path):
    return subprocess.run([REPO_ROOT, path], capture_output=True, text=True, timeout=20)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.main = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.main, "sub"))
        git("init", "-q", "-b", "main", cwd=self.main)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.main)
        self.wt = os.path.join(self.tmp, "proj-worktrees", "feat")
        git("worktree", "add", "-q", "-b", "feat", self.wt, cwd=self.main)

    def tearDown(self):
        subprocess.run(["rm", "-rf", self.tmp])


class RepoRoot(Fixture):
    def test_main_checkout(self):
        r = repo_root(self.main)
        self.assertEqual(r.stdout.split("\n")[0], self.main)

    def test_subdir_resolves_to_toplevel(self):
        self.assertEqual(repo_root(os.path.join(self.main, "sub")).stdout.split("\n")[0], self.main)

    def test_worktree_resolves_to_main_checkout(self):
        self.assertEqual(repo_root(self.wt).stdout.split("\n")[0], self.main)

    def test_prints_codebase_memory_project_name(self):
        lines = repo_root(self.wt).stdout.split("\n")
        self.assertEqual(lines[1], self.main.lstrip("/").replace("/", "-"))

    def test_outside_git_fails(self):
        r = repo_root(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")


class IndexRepoRewrite(Fixture):
    def run_hook(self, repo_path):
        payload = {"tool_name": "mcp__codebase-memory-mcp__index_repository",
                   "tool_input": {"repo_path": repo_path, "mode": "fast"}}
        return subprocess.run([sys.executable, REWRITE], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=20)

    def test_worktree_path_rewritten_to_main(self):
        r = self.run_hook(self.wt)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["updatedInput"], {"repo_path": self.main, "mode": "fast"})

    def test_rewrite_leaves_the_permission_decision_to_the_normal_flow(self):
        out = json.loads(self.run_hook(self.wt).stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertIn(self.main, out["additionalContext"])
        self.assertIn(self.wt, out["additionalContext"])

    def test_context_is_conditional_on_the_runtime_applying_the_update(self):
        text = json.loads(self.run_hook(self.wt).stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("if your harness applies", text)
        self.assertIn("confirm", text)
        self.assertIn(self.wt, text)
        self.assertIn(self.main, text)

    def test_readme_flags_the_behaviour_as_unverified_and_claude_only(self):
        readme = os.path.join(HOOKS, "..", "README.md")
        with open(readme) as f:
            text = f.read().lower()
        self.assertIn("code-graph-index-rewrite", text)
        self.assertIn("unverified", text)
        self.assertIn("claude code only", text)

    def test_subdirectory_of_main_is_a_deliberate_index_and_untouched(self):
        self.assertEqual(self.run_hook(os.path.join(self.main, "sub")).stdout, "")

    def test_subdirectory_of_a_linked_worktree_is_untouched(self):
        sub = os.path.join(self.wt, "sub")
        os.makedirs(sub)
        self.assertEqual(self.run_hook(sub).stdout, "")

    def test_main_path_untouched(self):
        self.assertEqual((self.run_hook(self.main).returncode, self.run_hook(self.main).stdout), (0, ""))

    def test_non_git_path_untouched(self):
        self.assertEqual(self.run_hook(self.tmp).stdout, "")

    def test_malformed_input_fails_open(self):
        for raw in ("", "not json", "[]", '{"tool_input":{}}'):
            with self.subTest(raw=raw):
                r = subprocess.run([sys.executable, REWRITE], input=raw, capture_output=True, text=True)
                self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
