"""Table-driven tests for hooks/pr-poll-reminder. Run: python3 -m unittest discover -s hooks/tests -v"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pr-poll-reminder")
_loader = importlib.machinery.SourceFileLoader("pr_poll_reminder", HOOK)
_spec = importlib.util.spec_from_loader("pr_poll_reminder", _loader)
reminder = importlib.util.module_from_spec(_spec)
_loader.exec_module(reminder)

# (command, has_pr_status_call, has_loop_word)
CASES = [
    ("gh pr view feat --json state -q .state", True, False),
    ("gh pr checks feat", True, False),
    ("gh pr view feat --json state,mergedAt", True, False),
    ("while :; do gh pr view feat --json state -q .state; sleep 10; done", True, True),
    ("until gh pr view feat --json state | grep -q MERGED; do sleep 5; done", True, True),
    ("gh pr view feat", False, False),  # no --json state: a plain status check, not polling
    ("gh pr list", False, False),
    ("gh pr create --title t", False, False),
    ("echo 'gh pr view feat --json state'", False, False),  # quoted text must not trigger
    ("git commit -m 'while true; do gh pr view x; done'", False, False),
]


class AnalyzeTable(unittest.TestCase):
    def test_table(self):
        for command, want_call, want_loop in CASES:
            with self.subTest(command=command):
                has_call, has_loop = reminder.analyze(command)
                self.assertEqual(has_call, want_call)
                self.assertEqual(has_loop, want_loop)


# (command, is_pr_create)
CREATE_CASES = [
    ("gh pr create --draft --title t --body b", True),
    ("cd wt && gh pr create --fill", True),
    ("GH_REPO=o/r gh pr create --title t", True),
    ("glab mr create --draft --fill", True),
    ("gh pr list", False),
    ("glab mr list", False),
    ("echo 'gh pr create'", False),  # quoted text must not trigger
]


class CreateTable(unittest.TestCase):
    def test_table(self):
        for command, want in CREATE_CASES:
            with self.subTest(command=command):
                self.assertEqual(reminder.analyze_create(command), want)


# (command, is_poll_loop): a loop that sleeps and re-reads CI or PR state. Needs a sleep: a plain
# `for` over repos that lists PRs is a sweep, not a poll.
LOOP_POLL_CASES = [
    ("while :; do gh run list --limit 1; sleep 20; done", True),
    ("until gh api repos/o/r/pulls/5 | jq -e .merged; do sleep 5; done", True),
    ("for i in 1 2 3; do gh pr list; sleep 5; done", True),
    ("while :; do gh run view 123 --json status; sleep 10; done", True),
    ("for r in a b; do gh pr list -R $r; done", False),  # sweep: no sleep
    ("for r in a b; do gh pr list -R $r; sleep 1; done", False),  # a paced sweep over names is still a sweep
    ("for i in $(seq 1 30); do gh run list; sleep 5; done", True),  # counting loop: a poll
    ("gh run list --limit 3", False),  # bare call
    ("while read r; do gh pr list -R $r; done < repos.txt", False),  # no sleep
    ("until curl -sf localhost:8080; do sleep 2; done", False),  # not a gh call
]


class LoopPollTable(unittest.TestCase):
    def test_table(self):
        for command, want in LOOP_POLL_CASES:
            with self.subTest(command=command):
                self.assertEqual(reminder.analyze_loop_poll(command), want)


def decision(stdout):
    return json.loads(stdout)["hookSpecificOutput"].get("permissionDecision")


class EndToEnd(unittest.TestCase):
    def run_hook(self, payload, raw=None, env=None):
        return subprocess.run(
            [sys.executable, HOOK],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, timeout=20,
            env={**os.environ, **(env or {})},
        )

    def test_loop_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "l1",
                       "tool_input": {"command": "while :; do gh pr view x --json state; sleep 5; done"}}
            r = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)["hookSpecificOutput"]
            self.assertEqual(out["hookEventName"], "PreToolUse")
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertIn("scripts/babysit", out["permissionDecisionReason"])

    def test_bare_call_nudges_second_then_denies_third(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "s1",
                       "tool_input": {"command": "gh pr view x --json state -q .state"}}
            r1 = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual((r1.returncode, r1.stdout), (0, ""))
            r2 = self.run_hook(payload, env={"TMPDIR": tmp})
            out = json.loads(r2.stdout)["hookSpecificOutput"]
            self.assertIsNone(out.get("permissionDecision"))
            self.assertIn("scripts/babysit", out["additionalContext"])
            r3 = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual(decision(r3.stdout), "deny")

    def seed_counter(self, tmp, session, ages):
        """Write a per-session counter file holding one status call per age (seconds ago)."""
        import time
        path = os.path.join(tmp, f"agent-pr-poll-reminder.{session}")
        with open(path, "w") as f:
            f.write("".join(f"{time.time() - a}\n" for a in ages))

    def test_counter_is_append_only_one_line_per_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(3):
                self.run_hook({"tool_name": "Bash", "session_id": "ap",
                               "tool_input": {"command": "gh pr checks 9"}}, env={"TMPDIR": tmp})
            with open(os.path.join(tmp, "agent-pr-poll-reminder.ap")) as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 3)
            [float(ln) for ln in lines]

    def test_a_partial_trailing_line_does_not_reset_the_count(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TMPDIR"] = tmp
            try:
                now = time.time()
                with open(os.path.join(tmp, "agent-pr-poll-reminder.pl"), "w") as f:
                    f.write(f"{now - 20}\n{now - 10}\n12.3gar")  # a writer died mid-line
                self.assertEqual(reminder.record_status_call("pl", now), 3)
            finally:
                del os.environ["TMPDIR"]

    def test_interleaved_writers_lose_no_call(self):
        import threading
        import time
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TMPDIR"] = tmp
            try:
                gate = threading.Barrier(8)

                def writer():
                    gate.wait()
                    for _ in range(25):
                        reminder.record_status_call("cc", time.time())
                threads = [threading.Thread(target=writer) for _ in range(8)]
                [t.start() for t in threads]
                [t.join() for t in threads]
                self.assertEqual(reminder.record_status_call("cc", time.time()), 8 * 25 + 1)
            finally:
                del os.environ["TMPDIR"]

    def test_status_calls_an_hour_apart_are_never_denied(self):
        # Three bare reads spread over hours are routine status checks, not a poll.
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "d1",
                       "tool_input": {"command": "gh pr view x --json state -q .state"}}
            self.seed_counter(tmp, "d1", [7200, 3700])
            r = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual((r.returncode, r.stdout), (0, ""))
            self.seed_counter(tmp, "d1", [9000, 7200, 3700, 3650, 3600])
            r = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_three_status_calls_within_ten_minutes_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "d2",
                       "tool_input": {"command": "gh pr checks 9"}}
            self.seed_counter(tmp, "d2", [90, 30])
            r = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual(decision(r.stdout), "deny")

    def test_empty_tmpdir_does_not_write_into_the_project(self):
        with tempfile.TemporaryDirectory() as proj:
            payload = {"tool_name": "Bash", "session_id": "e1", "tool_input": {"command": "gh pr checks 9"}}
            subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True,
                           cwd=proj, timeout=20, env={**os.environ, "TMPDIR": ""})
            self.assertEqual(os.listdir(proj), [])

    def test_session_id_cannot_escape_the_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "../../evil", "tool_input": {"command": "gh pr checks 9"}}
            self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertFalse(os.path.exists(os.path.join(tmp, "..", "..", "evil")))
            self.assertEqual(len(os.listdir(tmp)), 1)

    def test_old_integer_counter_file_is_ignored_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "agent-pr-poll-reminder.d3"), "w") as f:
                f.write("7")  # the previous format
            payload = {"tool_name": "Bash", "session_id": "d3",
                       "tool_input": {"command": "gh pr checks 9"}}
            r = self.run_hook(payload, env={"TMPDIR": tmp})
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_poll_denial_names_the_scripts_beside_the_hook(self):
        # The plugin ships skills/workflow/scripts next to hooks/: the path comes from the hook's own
        # location, never from ~/.claude.
        scripts = os.path.join(os.path.realpath(os.path.join(os.path.dirname(HOOK))), "..", "skills", "workflow", "scripts")
        scripts = os.path.realpath(scripts)
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"tool_name": "Bash", "session_id": "d4",
                       "tool_input": {"command": "while :; do gh pr view x --json state; sleep 5; done"}}
            r = self.run_hook(payload, env={"TMPDIR": tmp, "HOME": tmp})
            reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn(os.path.join(scripts, "babysit"), reason)
            self.assertIn(os.path.join(scripts, "pr-state"), reason)
            self.assertIn("persistent", reason)  # the Monitor call shape that avoids re-arming every 30 minutes

    def test_poll_denial_without_the_skill_names_it_by_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            lone = os.path.join(tmp, "plugin", "hooks")
            os.makedirs(lone)
            shutil.copy(HOOK, os.path.join(lone, "pr-poll-reminder"))
            payload = {"tool_name": "Bash", "session_id": "d5",
                       "tool_input": {"command": "while :; do gh pr view x --json state; sleep 5; done"}}
            r = subprocess.run([sys.executable, os.path.join(lone, "pr-poll-reminder")], input=json.dumps(payload),
                               capture_output=True, text=True, timeout=20, env={**os.environ, "TMPDIR": tmp})
            reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("git:workflow's scripts/babysit", reason)
            self.assertNotIn(tmp, reason)

    def test_foreground_sleep_is_not_this_hooks_concern(self):
        # The generic no-sleep rule belongs to the plugin that owns waiting, not to git.
        for command in ("sleep 20; ps aux | grep cargo", "sleep 61", "sleep 30; tail -n 20 task.output"):
            with self.subTest(command=command):
                r = self.run_hook({"tool_name": "Bash", "session_id": "w1", "tool_input": {"command": command}})
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_counter_file_uses_the_agent_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_hook({"tool_name": "Bash", "session_id": "p1",
                           "tool_input": {"command": "gh pr checks 9"}}, env={"TMPDIR": tmp})
            self.assertEqual(os.listdir(tmp), ["agent-pr-poll-reminder.p1"])

    def test_heredoc_strip_is_linear_on_hostile_input(self):
        import time
        for cmd in ("cat <<EOF\n" + " \n" * 100000, "cat <<EOF\n" * 20000, "x" * 300000):
            t = time.time()
            reminder.analyze_loop_poll(cmd)
            # Catches a quadratic strip; the 2s bound flaked on a loaded CI runner (2.05s).
            self.assertLess(time.time() - t, 10.0)

    def test_gh_poll_loop_is_denied(self):
        r = self.run_hook({"tool_name": "Bash", "session_id": "l2",
                           "tool_input": {"command": "while :; do gh run list --limit 1; sleep 20; done"}})
        self.assertEqual(decision(r.stdout), "deny")

    def test_repo_sweep_with_for_loop_is_allowed(self):
        r = self.run_hook({"tool_name": "Bash", "session_id": "l3",
                           "tool_input": {"command": "for r in a b; do gh pr list -R $r; done"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_pr_create_nudges_babysit(self):
        r = self.run_hook({"tool_name": "Bash", "session_id": "c1",
                           "tool_input": {"command": "gh pr create --draft --title t --body b"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertIn("scripts/babysit", out["additionalContext"])

    def test_unrelated_command_silent(self):
        r = self.run_hook({"tool_name": "Bash", "session_id": "s2", "tool_input": {"command": "gh pr list"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_other_tool_ignored(self):
        r = self.run_hook({"tool_name": "Read", "tool_input": {"command": "gh pr view x --json state"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_malformed_input_fails_open(self):
        for raw in ("", "not json", "[]", '{"tool_name":"Bash"}'):
            with self.subTest(raw=raw):
                r = self.run_hook(None, raw=raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
