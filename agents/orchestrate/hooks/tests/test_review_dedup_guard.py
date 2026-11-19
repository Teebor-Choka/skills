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


class Decide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def d(self, prompt, session="s1", description=""):
        return rdg.decide(agent(prompt, description), session, self.tmp)[0]

    def test_first_allowed_second_ask_third_deny(self):
        self.assertEqual(self.d("review PR #571"), "")
        self.assertEqual(self.d("Review pull request #571 again"), "ask")
        self.assertEqual(self.d("audit https://github.com/o/r/pull/571"), "deny")
        self.assertEqual(self.d("review #571"), "deny")

    def test_reason_names_pr_and_alternative(self):
        self.d("review #571")
        _, reason = rdg.decide(agent("review #571"), "s1", self.tmp)
        self.assertIn("571", reason)
        self.assertIn("already", reason)

    def test_different_pr_or_session_independent(self):
        self.assertEqual(self.d("review #571"), "")
        self.assertEqual(self.d("review #572"), "")
        self.assertEqual(self.d("review #571", session="s2"), "")

    def test_non_review_or_no_pr_never_counts(self):
        for _ in range(5):
            self.assertEqual(self.d("fix the bug in #571"), "")
            self.assertEqual(self.d("review the architecture"), "")
        self.assertEqual(self.d("review #571"), "")

    def test_description_counts_too(self):
        self.assertEqual(self.d("look at it", description="Review PR #9"), "")
        self.assertEqual(self.d("look at it", description="Review PR #9"), "ask")

    def test_multi_pr_uses_worst(self):
        self.d("review #1")
        self.d("review #1")
        self.assertEqual(self.d("review #1 and #2"), "deny")

    def test_hostile_session_ids_and_empty_tmpdir(self):
        for sid in ["../../etc/x", "a/b", "", None, "x" * 500, "\x00"]:
            with self.subTest(sid=sid):
                rdg.decide(agent("review #3"), sid, self.tmp)
        os.environ.pop("TMPDIR", None)
        self.assertIn(rdg.decide(agent("review #3"), "s", "")[0], ("", "ask", "deny"))
        self.assertEqual(os.listdir(self.tmp).count("etc"), 0)
        self.assertTrue(all(os.sep not in n for n in os.listdir(self.tmp)))

    def test_state_file_uses_agent_prefix(self):
        self.d("review #8", session="pfx")
        self.assertEqual(os.listdir(self.tmp), ["agent-review-dedup.pfx.json"])

    def test_reason_names_no_private_tooling(self):
        self.d("review #8")
        self.d("review #8")
        _, reason = rdg.decide(agent("review #8"), "s1", self.tmp)
        self.assertNotIn("review-lease", reason)

    def test_no_session_id_gets_a_per_user_per_cwd_file(self):
        tmp = tempfile.mkdtemp()
        for cwd in ("/a", "/b"):
            run_hook({"tool_name": "Agent", "cwd": cwd, "tool_input": {"prompt": "review PR #77"}}, tmp)
        names = sorted(os.listdir(tmp))
        self.assertEqual(len(names), 2)
        for name in names:
            self.assertTrue(name.startswith("agent-review-dedup.nosession-%d-" % os.getuid()), name)

    def test_planted_symlink_is_not_followed(self):
        tmp = tempfile.mkdtemp()
        victim = os.path.join(tmp, "victim")
        with open(victim, "w") as f:
            f.write("keep")
        os.symlink(victim, os.path.join(tmp, "agent-review-dedup.sl.json"))
        p = {"tool_name": "Agent", "session_id": "sl", "tool_input": {"prompt": "review PR #77"}}
        self.assertEqual(run_hook(p, tmp)[0], 0)
        with open(victim) as f:
            self.assertEqual(f.read(), "keep")

    def test_corrupt_counter_file_fails_open(self):
        self.d("review #5", session="c")
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("{not json")
        self.assertEqual(self.d("review #5", session="c"), "")


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
        rc, out = run_hook(p, tmp)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        rc, out = run_hook(p, tmp)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

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
