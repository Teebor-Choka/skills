"""Table-driven tests for hooks/mcp-bash-reminder. Run: python3 -m pytest hooks/tests"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

from cg_support import Sandbox

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp-bash-reminder")
_loader = importlib.machinery.SourceFileLoader("mcp_bash_reminder", HOOK)
_spec = importlib.util.spec_from_loader("mcp_bash_reminder", _loader)
reminder = importlib.util.module_from_spec(_spec)
_loader.exec_module(reminder)

# (command, expect a sweep)
CASES = [
    # sweeps: fire
    ("grep -r foo src/", True),
    ("grep -R foo .", True),
    ("grep --include=*.rs -n foo .", True),
    ("rg foo", True),
    ("rg foo src/", True),
    ("ag foo", True),
    ("find . -name '*.rs'", True),
    ("find . -iname '*.py'", True),
    ("cd src && grep -r foo .", True),
    ("FOO=1 grep -r foo .", True),
    ("env FOO=1 rg foo", True),
    ('bash -c "grep -r foo ."', True),
    ("git log | grep -r foo", True),  # any segment matching fires
    # not sweeps: stay silent
    ("grep foo file.rs", False),
    ("cat file.rs", False),
    ("grep -n foo file.rs", False),
    ("find . -maxdepth 1", False),
    ("git log | grep foo", False),
    ("echo 'grep -r foo .'", False),  # quoted text must not trigger
    ("git commit -m 'rg foo'", False),
    ("ls -la", False),
]


class IsSweepTable(unittest.TestCase):
    def test_table(self):
        for command, want in CASES:
            with self.subTest(command=command):
                self.assertEqual(reminder.is_sweep(command), want)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def payload(self, session="s1", cwd=None, command="grep -r foo ."):
        p = {"tool_name": "Bash", "session_id": session, "tool_input": {"command": command}}
        if cwd != "":
            p["cwd"] = cwd or self.sb.repo
        return p

    def run_hook(self, payload, sb=None, **env):
        return (sb or self.sb).run(HOOK, payload, **env)

    def test_fires_once_per_session_in_git_repo(self):
        r1 = self.run_hook(self.payload())
        self.assertEqual(r1.returncode, 0, r1.stderr)
        out = json.loads(r1.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("codebase-memory-mcp", out["additionalContext"])
        r2 = self.run_hook(self.payload())
        self.assertEqual((r2.returncode, r2.stdout), (0, ""))

    def test_silent_outside_git_repo(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        r = self.run_hook(self.payload(cwd=plain))
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_silent_when_not_a_sweep(self):
        r = self.run_hook(self.payload(command="cat file.rs"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_other_tool_ignored(self):
        r = self.run_hook({"tool_name": "Grep", "tool_input": {"command": "grep -r foo ."}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_malformed_input_fails_open(self):
        for raw in ("", "not json", "[]", '{"tool_name":"Bash"}'):
            with self.subTest(raw=raw):
                r = self.run_hook(raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_path_missing_is_silent(self):
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        r = self.run_hook(self.payload(cwd=sb.repo), sb=sb)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_payload_cwd_wins_over_project_dir_env(self):
        r = self.run_hook(self.payload(), CLAUDE_PROJECT_DIR="/nonexistent")
        self.assertIn("additionalContext", r.stdout)

    def test_marker_uses_agent_prefix(self):
        self.run_hook(self.payload(session="pfx"))
        self.assertEqual(os.listdir(self.sb.tmp).count("agent-mcp-bash-reminder.pfx"), 1)
        self.assertEqual([n for n in os.listdir(self.sb.tmp) if n.startswith("claude-")], [])

    def test_empty_tmpdir_falls_back_to_tmp(self):
        sid = "empty-tmp-" + os.path.basename(self.sb.tmp)
        before = set(os.listdir(os.getcwd()))
        r = self.run_hook(self.payload(session=sid), TMPDIR="")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(os.listdir(os.getcwd())), before)
        marker = "/tmp/agent-mcp-bash-reminder." + sid
        if os.path.exists(marker):  # the hook's own residue, when /tmp exists
            os.unlink(marker)

    def subdir(self):
        d = os.path.join(self.sb.repo, "sub")
        os.makedirs(d, exist_ok=True)
        return d

    def test_no_session_id_gets_a_per_user_per_cwd_marker(self):
        for cwd in (self.sb.repo, self.subdir()):
            p = self.payload(cwd=cwd)
            del p["session_id"]
            self.run_hook(p)
        names = [n for n in os.listdir(self.sb.tmp) if n.startswith("agent-mcp-bash-reminder.")]
        self.assertEqual(len(names), 2, names)
        for name in names:
            self.assertTrue(name.startswith("agent-mcp-bash-reminder.nosession-%d-" % os.getuid()), name)

    def test_session_id_is_sanitised_like_the_other_hooks(self):
        self.run_hook(self.payload(session="../../escape x"))
        self.assertIn("agent-mcp-bash-reminder._.._escape_x", os.listdir(self.sb.tmp))

    def test_planted_symlink_is_not_followed(self):
        victim = os.path.join(self.sb.tmp, "victim")
        with open(victim, "w") as f:
            f.write("keep")
        os.symlink(victim, os.path.join(self.sb.tmp, "agent-mcp-bash-reminder.sl"))
        r = self.run_hook(self.payload(session="sl"))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "keep")


if __name__ == "__main__":
    unittest.main()
