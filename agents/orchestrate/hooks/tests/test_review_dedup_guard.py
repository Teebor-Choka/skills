"""Tests for hooks/review-dedup-guard. Run: python3 -m pytest hooks/tests"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "review-dedup-guard")
_loader = importlib.machinery.SourceFileLoader("review_dedup_guard", HOOK)
_spec = importlib.util.spec_from_loader("review_dedup_guard", _loader)
rdg = importlib.util.module_from_spec(_spec)
_loader.exec_module(rdg)


def agent(prompt, description=""):
    return {"prompt": prompt, "description": description}


class PrRefs(unittest.TestCase):
    def test_extracts(self):
        cases = [
            ("review PR #571", {"571"}),
            ("Review PR 571 uid refusal", {"571"}),
            ("review pr571", {"571"}),
            ("review PR-571", {"571"}),
            ("review https://github.com/o/r/pull/571/files", {"571"}),
            ("audit #12 and #13", {"12", "13"}),
            ("review the payments repo", set()),
            ("review issue #", set()),
            ("pr review", set()),
            ("order 5 items", set()),
            ("review src/a.rs per the rules in #1", set()),
            ("review the module, see #1 for the rules", set()),
            ("audit the auth code against issue #12", set()),
            ("review item #3", set()),
            ("review pr #4 against the rules in #1", {"4"}),
        ]
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(rdg.pr_refs(text), want)

    def test_cap_and_long_input(self):
        refs = rdg.pr_refs(" ".join(f"#{i}" for i in range(1, 500)))
        self.assertLessEqual(len(refs), 20)
        rdg.pr_refs("pr" + " " * 300_000 + "1")
        rdg.pr_refs("#" * 300_000)
        rdg.pr_refs("pr-" * 100_000)

    def test_is_review(self):
        for text, want in [("review PR", True), ("Reviewer for 5", True), ("audit it", True), ("reviewing", True),
                           ("preview", False), ("fix PR #5", False), ("", False)]:
            with self.subTest(text=text):
                self.assertEqual(rdg.is_review(text), want)


class IsReview(unittest.TestCase):
    def test_review_as_the_task_counts(self):
        for text in ("review PR #5", "Please audit pull request 5", "code review of PR 5", "do a review of PR 5"):
            with self.subTest(text=text):
                self.assertTrue(rdg.is_review(text))

    def test_acting_on_review_comments_is_not_a_review_task(self):
        for text in ("address review comments on PR 12", "fix the review feedback on PR 12",
                     "respond to review threads on PR 12", "resolve the review comments on PR 12",
                     "apply the reviewer suggestions on PR 12", "reply to the review comments on PR 12"):
            with self.subTest(text=text):
                self.assertFalse(rdg.is_review(text))


class Decide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def d(self, prompt, session="s1", description="", nested=False):
        return rdg.decide(agent(prompt, description), session, self.tmp, nested=nested)[0]

    def test_first_and_second_pass_third_asks_fourth_denies(self):
        self.assertEqual(self.d("review PR #571"), "")
        self.assertEqual(self.d("Review pull request #571 again"), "")
        self.assertEqual(self.d("audit https://github.com/o/r/pull/571"), "ask")
        self.assertEqual(self.d("review #571 once more, review PR 571"), "deny")
        self.assertEqual(self.d("review PR #571"), "deny")

    def test_reason_names_pr_and_alternative(self):
        for _ in range(3):
            self.d("review PR #571")
        _, reason = rdg.decide(agent("review PR #571"), "s1", self.tmp)
        self.assertIn("571", reason)
        self.assertIn("already", reason)

    def test_different_pr_or_session_independent(self):
        for _ in range(3):
            self.d("review PR #571")
        self.assertEqual(self.d("review PR #572"), "")
        self.assertEqual(self.d("review PR #571", session="s2"), "")

    def test_non_review_or_no_pr_never_counts(self):
        for _ in range(6):
            self.assertEqual(self.d("fix the bug in PR #571"), "")
            self.assertEqual(self.d("review the architecture"), "")
        self.assertEqual(self.d("review PR #571"), "")

    def test_addressing_review_comments_never_counts(self):
        for _ in range(6):
            self.assertEqual(self.d("address review comments on PR 12"), "")
        self.assertEqual(self.d("review PR 12"), "")
        self.assertEqual(self.d("review PR 12"), "")

    def test_nested_spawns_are_not_counted(self):
        for _ in range(6):
            self.assertEqual(self.d("review PR #9", nested=True), "")
        self.assertEqual(self.d("review PR #9"), "")
        self.assertEqual(self.d("review PR #9"), "")

    def test_fan_out_of_six_agents_for_one_pr_is_allowed(self):
        prompts = ["Review PR 77: find bugs (finder A)", "Review PR 77: find bugs (finder B)",
                   "Review PR 77: find bugs (finder C)", "Verify finding 1 of the review of PR 77 (verifier)",
                   "Verify finding 2 of the review of PR 77 (verifier)", "Verify finding 3 of the review of PR 77 (verifier)"]
        self.assertEqual([self.d(p) for p in prompts], [""] * 6)
        self.assertEqual(self.d("review PR 77"), "ask")  # the fan-out counted once per role: 2 so far, this is the 3rd

    def test_description_counts_too(self):
        self.assertEqual(self.d("look at it", description="Review PR #9"), "")
        self.assertEqual(self.d("look at it", description="Review PR #9"), "")
        self.assertEqual(self.d("look at it", description="Review PR #9"), "ask")

    def test_multi_pr_uses_worst(self):
        for _ in range(3):
            self.d("review PR #1")
        self.assertEqual(self.d("review PR #1 and PR #2"), "deny")

    def test_state_is_one_line_per_event_and_append_only(self):
        for _ in range(3):
            self.d("review PR #8", session="pfx")
        (name,) = os.listdir(self.tmp)
        self.assertEqual(name, "agent-review-dedup.pfx.log")
        with open(os.path.join(self.tmp, name)) as f:
            self.assertEqual(len(f.read().splitlines()), 3)

    def test_partial_line_does_not_reset_the_count(self):
        self.d("review PR #8", session="pl")
        self.d("review PR #8", session="pl")
        with open(os.path.join(self.tmp, "agent-review-dedup.pl.log"), "a") as f:
            f.write("8\t")  # a torn write from a crashed writer
        self.assertEqual(self.d("review PR #8", session="pl"), "ask")

    def test_two_interleaved_writers_lose_no_event(self):
        import threading

        def writer(tag):
            for i in range(25):
                rdg.decide(agent(f"review PR #{tag}{i}"), "race", self.tmp)

        threads = [threading.Thread(target=writer, args=(t,)) for t in ("1", "2", "3")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with open(os.path.join(self.tmp, "agent-review-dedup.race.log")) as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 75)
        self.assertEqual(len(set(lines)), 75)

    def test_hostile_session_ids_and_empty_tmpdir(self):
        for sid in ["../../etc/x", "a/b", "", None, "x" * 500, "\x00"]:
            with self.subTest(sid=sid):
                rdg.decide(agent("review PR #3"), sid, self.tmp)
        self.assertIn("agent-review-dedup._.._etc_x.log", os.listdir(self.tmp))
        self.assertTrue(all(os.sep not in n for n in os.listdir(self.tmp)))
        self.assertEqual(rdg.counter_path("s", ""), "/tmp/agent-review-dedup.s.log")
        self.assertEqual(rdg.counter_path("s", None), "/tmp/agent-review-dedup.s.log")

    def test_no_session_id_gets_a_per_user_per_cwd_file(self):
        tmp = tempfile.mkdtemp()
        for cwd in ("/a", "/b"):
            run_hook({"tool_name": "Agent", "cwd": cwd, "tool_input": {"prompt": "review PR #77"}}, tmp)
        names = sorted(os.listdir(tmp))
        self.assertEqual(len(names), 2)
        for name in names:
            self.assertTrue(name.startswith("agent-review-dedup.nosession-%d-" % os.getuid()), name)

    def test_planted_symlink_is_not_followed(self):
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as f:
            f.write("keep")
        os.symlink(victim, os.path.join(self.tmp, "agent-review-dedup.sl.log"))
        p = {"tool_name": "Agent", "session_id": "sl", "tool_input": {"prompt": "review PR #77"}}
        self.assertEqual(run_hook(p, self.tmp)[0], 0)
        with open(victim) as f:
            self.assertEqual(f.read(), "keep")

    def test_corrupt_counter_file_fails_open(self):
        self.d("review PR #5", session="c")
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("{not json\n\x00\xff")
        self.assertEqual(self.d("review PR #5", session="c"), "")


def run_hook(payload, tmpdir):
    env = {**os.environ, "TMPDIR": tmpdir}
    r = subprocess.run([sys.executable, HOOK], input=payload if isinstance(payload, str) else json.dumps(payload),
                       capture_output=True, text=True, timeout=20, env=env)
    return r.returncode, r.stdout


class EndToEnd(unittest.TestCase):
    def test_flow(self):
        tmp = tempfile.mkdtemp()
        p = {"tool_name": "Agent", "session_id": "e2e", "tool_input": {"prompt": "review PR #77", "model": "opus"}}
        self.assertEqual(run_hook(p, tmp)[1].strip(), "")
        self.assertEqual(run_hook(p, tmp)[1].strip(), "")
        rc, out = run_hook(p, tmp)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        rc, out = run_hook(p, tmp)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_a_subagent_spawn_is_not_counted(self):
        tmp = tempfile.mkdtemp()
        p = {"tool_name": "Agent", "session_id": "nest", "agent_id": "a1", "tool_input": {"prompt": "review PR #77"}}
        for _ in range(6):
            self.assertEqual(run_hook(p, tmp)[1].strip(), "")
        self.assertEqual(os.listdir(tmp), [])

    def test_other_tools_and_malformed_fail_open(self):
        tmp = tempfile.mkdtemp()
        for bad in ["", "nope", "[]", json.dumps({"tool_name": "Bash", "tool_input": {"prompt": "review #1"}}),
                    json.dumps({"tool_name": "Agent", "tool_input": "x"}),
                    json.dumps({"tool_name": "Agent", "tool_input": {"prompt": 5}})]:
            with self.subTest(bad=bad):
                rc, out = run_hook(bad, tmp)
                self.assertEqual((rc, out.strip()), (0, ""))


if __name__ == "__main__":
    unittest.main()
