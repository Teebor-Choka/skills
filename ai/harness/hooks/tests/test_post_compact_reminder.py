"""Tests for hooks/post-compact-reminder.sh. Run: python3 -m pytest hooks/tests"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "post-compact-reminder.sh")


def run():
    r = subprocess.run([HOOK], input="{}", capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]


class PostCompact(unittest.TestCase):
    def test_e7_works_without_jq_on_the_path(self):
        bindir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bindir)
        for tool in ("python3", "bash", "env", "sh"):
            found = shutil.which(tool)
            if found:
                os.symlink(found, os.path.join(bindir, tool))
        self.assertIsNone(shutil.which("jq", path=bindir))
        r = subprocess.run([HOOK], input="{}", capture_output=True, text=True, timeout=20,
                           env={"PATH": bindir, "HOME": bindir})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("Re-Read a file before you Edit", out["additionalContext"])

    def test_e7_output_is_identical_with_and_without_jq(self):
        self.assertEqual(json.loads(subprocess.run([HOOK], input="{}", capture_output=True, text=True).stdout)
                         ["hookSpecificOutput"]["additionalContext"], run()["additionalContext"])

    def test_output_is_valid_sessionstart_json(self):
        self.assertEqual(run()["hookEventName"], "SessionStart")

    def test_keeps_the_file_state_reminder(self):
        self.assertIn("Re-Read a file before you Edit", run()["additionalContext"])

    def test_reminds_about_deferred_tools(self):
        ctx = run()["additionalContext"]
        self.assertIn("ToolSearch select:", ctx)
        self.assertIn("SendMessage", ctx)

    def test_warns_that_task_ids_go_stale(self):
        self.assertIn("task ids", run()["additionalContext"].lower())


if __name__ == "__main__":
    unittest.main()
