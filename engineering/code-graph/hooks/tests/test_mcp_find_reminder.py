"""Tests for hooks/mcp-find-reminder. Run: python3 -m pytest hooks/tests"""
import json
import os
import unittest

from cg_support import Sandbox

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp-find-reminder")


class McpFindReminder(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def run_hook(self, session="s1", sb=None, payload=None, **env):
        sb = sb or self.sb
        payload = {"tool_name": "Grep", "session_id": session, "cwd": sb.repo} if payload is None else payload
        return sb.run(HOOK, payload, **env)

    def test_nudge_cadence_is_1st_6th_16th(self):
        fired = [i + 1 for i in range(16) if self.run_hook().stdout]
        self.assertEqual(fired, [1, 6, 16])

    def test_nudge_is_additional_context(self):
        out = json.loads(self.run_hook().stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("search_graph", out["additionalContext"])

    def test_without_graph_binary_no_nudge(self):
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        self.assertEqual(self.run_hook(sb=sb).stdout, "")

    def test_silent_outside_a_repo(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(self.run_hook(payload={"session_id": "p", "cwd": plain}).stdout, "")

    def test_payload_cwd_wins_over_project_dir_env(self):
        self.assertTrue(self.run_hook(CLAUDE_PROJECT_DIR="/nonexistent").stdout)

    def test_falls_back_to_project_dir_env_without_cwd(self):
        r = self.run_hook(payload={"session_id": "e"}, CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertTrue(r.stdout)

    def test_counter_file_uses_agent_prefix_and_no_log_is_written(self):
        self.run_hook()
        self.assertEqual(os.listdir(self.sb.tmp).count("hook-fired.log"), 0)
        self.assertEqual([n for n in os.listdir(self.sb.tmp) if n.startswith("agent-mcp-find-reminder.")],
                         ["agent-mcp-find-reminder.s1"])
        self.assertEqual([n for n in os.listdir(self.sb.tmp) if n.startswith("claude-")], [])

    def test_hostile_session_id_stays_inside_tmpdir(self):
        self.run_hook(session="../../escape x")
        self.assertFalse(os.path.exists(os.path.join(self.sb.tmp, "..", "..", "escape x")))
        self.assertFalse(any(os.sep in name for name in os.listdir(self.sb.tmp)))
        self.assertTrue(os.path.exists(os.path.join(self.sb.tmp, "agent-mcp-find-reminder._.._escape_x")))

    def test_empty_tmpdir_falls_back_to_tmp(self):
        sid = "empty-tmp-" + os.path.basename(self.sb.tmp)
        before = set(os.listdir(os.getcwd()))
        r = self.run_hook(session=sid, TMPDIR="")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(os.listdir(os.getcwd())), before)
        marker = "/tmp/agent-mcp-find-reminder." + sid
        self.assertTrue(os.path.exists(marker))
        os.unlink(marker)

    def plant(self, content, session="plant"):
        with open(os.path.join(self.sb.tmp, "agent-mcp-find-reminder." + session), "w") as f:
            f.write(content)

    def test_hostile_counter_file_is_never_evaluated_as_arithmetic(self):
        side_effect = os.path.join(self.sb.tmp, "pwned")
        self.plant("a[$(touch %s)]" % side_effect)
        r = self.run_hook(session="plant")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(side_effect))

    def test_non_numeric_counter_file_counts_as_zero(self):
        for content in ("1 2", "abc", "", "-1", "1\n2"):
            with self.subTest(content=content):
                self.plant(content)
                r = self.run_hook(session="plant")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(r.stdout, "counter reset to 0 means the next call is the 1st and nudges")

    def subdir(self):
        d = os.path.join(self.sb.repo, "sub")
        os.makedirs(d, exist_ok=True)
        return d

    def test_no_session_id_gets_a_per_user_per_cwd_counter(self):
        for cwd in (self.sb.repo, self.subdir()):
            self.run_hook(payload={"tool_name": "Grep", "cwd": cwd})
        names = [n for n in os.listdir(self.sb.tmp) if n.startswith("agent-mcp-find-reminder.")]
        self.assertEqual(len(names), 2, names)
        for name in names:
            self.assertTrue(name.startswith("agent-mcp-find-reminder.nosession-%d-" % os.getuid()), name)

    def test_planted_symlink_is_not_followed(self):
        victim = os.path.join(self.sb.tmp, "victim")
        with open(victim, "w") as f:
            f.write("keep")
        os.symlink(victim, os.path.join(self.sb.tmp, "agent-mcp-find-reminder.sl"))
        r = self.run_hook(session="sl")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "keep")


if __name__ == "__main__":
    unittest.main()
