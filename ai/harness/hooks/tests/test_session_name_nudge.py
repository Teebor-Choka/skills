"""Tests for hooks/session-name-nudge.py (UserPromptSubmit). Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "session-name-nudge.py")


class SessionNameNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_hook(self, session="s1", title=None, raw=None, tmpdir=None):
        payload = {"session_id": session, "hook_event_name": "UserPromptSubmit", "prompt": "hi"}
        if title is not None:
            payload["session_title"] = title
        return subprocess.run(
            [sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "TMPDIR": self.tmp.name if tmpdir is None else tmpdir})

    def context(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout:
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        return out["additionalContext"]

    def test_silent_before_the_third_prompt(self):
        self.assertIsNone(self.context(self.run_hook()))
        self.assertIsNone(self.context(self.run_hook()))

    def test_third_unnamed_prompt_nudges_a_name(self):
        self.run_hook()
        self.run_hook()
        ctx = self.context(self.run_hook())
        self.assertIn("/rename", ctx)
        self.assertIn("<repo>-<issue-or-topic>-<role>", ctx)

    def test_nudge_fires_once(self):
        for _ in range(3):
            self.run_hook()
        for _ in range(3):
            self.assertIsNone(self.context(self.run_hook()))

    def test_named_session_is_never_nudged(self):
        for _ in range(5):
            self.assertIsNone(self.context(self.run_hook(title="hooks-session-hygiene-builder")))

    def test_name_set_late_cancels_the_nudge(self):
        self.run_hook()
        self.run_hook(title="named")
        self.assertIsNone(self.context(self.run_hook()))

    def test_sessions_are_counted_separately(self):
        self.run_hook("a")
        self.run_hook("a")
        self.assertIsNone(self.context(self.run_hook("b")))
        self.assertIsNotNone(self.context(self.run_hook("a")))

    def test_blank_title_counts_as_unnamed(self):
        self.run_hook(title="")
        self.run_hook(title="  ")
        self.assertIsNotNone(self.context(self.run_hook(title="")))

    def test_malformed_input_is_silent(self):
        for raw in ("", "not json", "[]", "{}", '{"session_id": 5}'):
            with self.subTest(raw=raw):
                r = self.run_hook(raw=raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_session_id_cannot_escape_the_temp_dir(self):
        self.run_hook(session="../../evil")
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "..", "..", "evil")))
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)

    def test_d8_a_planted_symlink_is_not_followed(self):
        victim = os.path.join(self.tmp.name, "victim")
        with open(victim, "w") as f:
            f.write("VICTIM")
        os.symlink(victim, os.path.join(self.tmp.name, "agent-session-name-nudge.s1"))
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "VICTIM")

    def test_d8_counter_file_is_private(self):
        self.run_hook("p2")
        mode = os.stat(os.path.join(self.tmp.name, "agent-session-name-nudge.p2")).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_empty_tmpdir_does_not_write_into_the_project(self):
        self.addCleanup(lambda: os.path.exists("/tmp/agent-session-name-nudge.e1")
                        and os.remove("/tmp/agent-session-name-nudge.e1"))
        with tempfile.TemporaryDirectory() as proj:
            subprocess.run([sys.executable, HOOK], input=json.dumps({"session_id": "e1"}), capture_output=True,
                           text=True, cwd=proj, timeout=20, env={**os.environ, "TMPDIR": ""})
            self.assertEqual(os.listdir(proj), [])

    def test_counter_file_uses_the_agent_prefix(self):
        self.run_hook("p1")
        self.assertEqual(os.listdir(self.tmp.name), ["agent-session-name-nudge.p1"])

    def test_corrupt_counter_file_is_not_fatal(self):
        with open(os.path.join(self.tmp.name, "agent-session-name-nudge.c1"), "w") as f:
            f.write("{{{")
        r = self.run_hook("c1")
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
