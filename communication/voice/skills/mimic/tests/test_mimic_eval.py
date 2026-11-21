"""AT-7 to AT-13: judge order, report math, verdict, revision isolation, leak checks, runners, end to end."""

import json
import unittest
from collections import Counter

from mimic_fixtures import Sandbox, build_state, read_jsonl
import mimiclib  # noqa: E402  (path set by mimic_fixtures)

DIMS = ["voice", "length", "register", "habit", "temperament"]


def item(i, identified=False, picked="B", scores=4, band="short", channel="chat", excluded=None):
    sc = None if scores is None else {d: scores for d in DIMS}
    return {"id": f"i{i:03d}", "band": band, "channel": channel, "excluded": excluded,
            "identified": identified, "picked": picked, "scores": sc}


def balanced(n, n_correct, scores=4):
    """n scored items, n_correct of them identified, picks alternating A/B."""
    return [item(i, identified=i < n_correct, picked="AB"[i % 2], scores=scores) for i in range(n)]


class JudgeOrder(unittest.TestCase):
    def test_positions_are_seeded_reproducible_and_balanced(self):
        ids = [f"x{i}" for i in range(400)]
        a = [mimiclib.original_first(1337, 1, i) for i in ids]
        self.assertEqual(a, [mimiclib.original_first(1337, 1, i) for i in ids])
        self.assertNotEqual(a, [mimiclib.original_first(1338, 1, i) for i in ids])
        self.assertNotEqual(a, [mimiclib.original_first(1337, 2, i) for i in ids])
        self.assertTrue(160 < sum(a) < 240, sum(a))

    def test_always_a_judge_is_invalid(self):
        items = [item(i, identified=(i % 2 == 0), picked="A") for i in range(30)]
        s = mimiclib.summarize(items)
        self.assertEqual(s["pos_a_rate"], 1.0)
        self.assertEqual(s["verdict"], "INVALID")


class ReportMath(unittest.TestCase):
    def test_rates_means_breakdowns_and_worst(self):
        items = balanced(20, 10)
        items[0]["scores"] = {d: 1 for d in DIMS}
        items[1]["band"] = "long"
        items[1]["channel"] = "email"
        items[2]["scores"] = None  # unparseable rubric: zeros
        items[3]["identified"] = None  # unparseable pick: counted as identified
        items[3]["picked"] = None
        s = mimiclib.summarize(items)
        self.assertEqual(s["n_scored"], 20)
        self.assertAlmostEqual(s["id_rate"], 10 / 20)  # item 3 was already among the first 10
        self.assertAlmostEqual(s["dims"]["voice"], (1 + 0 + 4 * 18) / 20)
        self.assertAlmostEqual(s["mean_rubric"], (1 + 0 + 4 * 18) / 20)
        self.assertEqual(s["by_band"]["long"]["n"], 1)
        self.assertEqual(s["by_channel"]["email"]["n"], 1)
        self.assertEqual(s["by_band"]["short"]["n"], 19)
        self.assertEqual(s["worst"][:2], ["i002", "i000"])
        self.assertEqual(s["unparseable"], {"identify": 1, "score": 1})

    def test_unparseable_pick_counts_against_the_mimic(self):
        items = balanced(20, 0)
        for it in items[:5]:
            it["identified"], it["picked"] = None, None
        self.assertAlmostEqual(mimiclib.summarize(items)["id_rate"], 5 / 20)

    def test_excluded_items_are_not_scored(self):
        items = balanced(20, 10) + [item(99, excluded="point_leak")]
        s = mimiclib.summarize(items)
        self.assertEqual((s["n_total"], s["n_scored"]), (21, 20))
        self.assertEqual(s["excluded"], {"point_leak": 1})

    def test_short_exact_match_rate_is_reported_but_not_judged(self):
        items = balanced(20, 10)
        for k, it in enumerate(items[:8]):
            it["original"] = "Ship it."
            it["generated"] = "ship it" if k < 2 else "Send it over."
        items[8]["band"] = "long"
        items[8]["original"] = items[8]["generated"] = "same long text here"
        s = mimiclib.summarize(items)
        self.assertEqual(s["short_exact_match"], {"n": 8, "matches": 2, "rate": 0.25})
        self.assertEqual(s["verdict"], mimiclib.summarize(balanced(20, 10))["verdict"])


class Verdict(unittest.TestCase):
    def test_pass_at_the_thresholds(self):
        self.assertEqual(mimiclib.summarize(balanced(20, 13, scores=3.5))["verdict"], "PASS")

    def test_fail_just_above_id_rate(self):
        self.assertEqual(mimiclib.summarize(balanced(20, 14))["verdict"], "FAIL")

    def test_fail_on_rubric(self):
        s = mimiclib.summarize(balanced(20, 10, scores=3))
        self.assertEqual(s["verdict"], "FAIL")
        self.assertEqual(s["failed_dims"], [])  # 3.0 is at the floor, not below
        self.assertEqual(mimiclib.summarize(balanced(20, 10, scores=2))["failed_dims"], DIMS)

    def test_inconclusive_below_min_n(self):
        self.assertEqual(mimiclib.summarize(balanced(19, 9))["verdict"], "INCONCLUSIVE")

    def test_invalid_when_too_many_excluded(self):
        items = balanced(20, 10) + [item(100 + i, excluded="copied") for i in range(6)]
        self.assertEqual(mimiclib.summarize(items)["verdict"], "INVALID")

    def test_thresholds_are_configurable(self):
        t = dict(mimiclib.THRESHOLDS, max_id_rate=0.75, min_n=10)
        self.assertEqual(mimiclib.summarize(balanced(12, 9), t)["verdict"], "PASS")

    def test_caricature_fails(self):
        # A judge that reliably picks the generated one can tell them apart: two-sided band.
        s = mimiclib.summarize(balanced(20, 6))
        self.assertEqual(s["verdict"], "FAIL")
        self.assertTrue(any("caricature" in w for w in s["warnings"]))
        self.assertEqual(mimiclib.summarize(balanced(20, 7))["verdict"], "PASS")


class LeakChecks(unittest.TestCase):
    def test_emoji_only_messages_have_their_own_key_and_leak_check(self):
        self.assertLess(mimiclib.similarity("👍", "😂"), 0.7)
        self.assertEqual(mimiclib.similarity("👍", "👍 "), 1.0)
        self.assertEqual(len(set(mimiclib.near_dup_clusters(["👍", "😂", "🔥", "..."]))), 4)
        self.assertTrue(mimiclib.point_leaks("reacts with 👍", "👍"))
        self.assertFalse(mimiclib.point_leaks("reacts with approval", "👍"))

    def test_point_leak_rules(self):
        orig = "can we push the staging db fix to friday please"
        self.assertTrue(mimiclib.point_leaks("asks to push the staging db fix later", orig))
        self.assertFalse(mimiclib.point_leaks("asks to delay a database repair by some days", orig))
        self.assertTrue(mimiclib.point_leaks("replies sgtm to the plan", "sgtm"))
        self.assertFalse(mimiclib.point_leaks("agrees with the plan", "sgtm"))

    def test_copied_rule_only_for_long_originals(self):
        long = "I went through the budget this morning and the numbers hold up fine"
        self.assertTrue(mimiclib.copied(long + "!", long))
        self.assertFalse(mimiclib.copied("ok", "ok"))

    def test_sanitize_drops_quotes_and_held_out_spans(self):
        held = ["we are two days behind because the supplier changed"]
        reasons = [
            'too formal; the original said "two days behind" bluntly',
            "missing the two days behind because tone",
            "length right, opener wrong",
        ]
        out = mimiclib.sanitize_reasons(reasons, held)
        self.assertEqual(out, ["too formal; the original said bluntly", "length right, opener wrong"])


class Runners(unittest.TestCase):
    def test_claude_argv_is_isolated(self):
        argv = mimiclib.claude_argv("opus", "SYS")
        self.assertEqual(argv, ["claude", "-p", "--model", "opus", "--no-session-persistence", "--tools", "",
                                "--strict-mcp-config", "--setting-sources", "", "--system-prompt", "SYS"])

    def test_tier_resolution(self):
        self.assertEqual(mimiclib.resolve_model("reasoning", {}), ("opus", "reasoning"))
        self.assertEqual(mimiclib.resolve_model("haiku", {}), ("haiku", "light"))
        self.assertEqual(mimiclib.resolve_model("claude-x-1", {}), ("claude-x-1", None))

    def test_tiers_file_override(self):
        sb = Sandbox()
        try:
            f = sb.root / "tiers.json"
            f.write_text(json.dumps({"tiers": {"reasoning": {"claude": "fable", "codex": "TODO"},
                                               "execution": {"codex": "TODO"}}}))
            env = {"AGENT_TIERS_FILE": str(f)}
            self.assertEqual(mimiclib.resolve_model("reasoning", env), ("fable", "reasoning"))
            self.assertEqual(mimiclib.resolve_model("execution", env), ("sonnet", "execution"))
            self.assertEqual(mimiclib.resolve_model("reasoning", dict(env, AGENT_HARNESS="codex")), ("opus", "reasoning"))
        finally:
            sb.close()

    def test_default_roles_use_the_strongest_tier_for_judge_and_generator(self):
        self.assertEqual(mimiclib.ROLE_TIERS["judge"], "reasoning")
        self.assertEqual(mimiclib.ROLE_TIERS["generate"], "reasoning")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.state = build_state(self.sb)

    def tearDown(self):
        self.sb.close()

    def run_eval(self, *args):
        return self.sb.run("evaluate.py", "run", "--persona", "pat", "--runner", "stub", *args)

    def script(self, data):
        p = self.sb.root / "stub.json"
        p.write_text(json.dumps(data))
        return p

    def test_test_round_reports_a_verdict_once(self):
        r = self.run_eval("--slice", "test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"verdict: (PASS|FAIL|INCONCLUSIVE|INVALID)")
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertEqual(rep["n_total"], 20)
        self.assertEqual(Counter(x["id"] for x in read_jsonl(self.state / "rounds" / "test-1" / "items.jsonl")).most_common(1)[0][1], 1)
        self.assertFalse((self.state / "rounds" / "test-1" / "feedback.json").exists())
        self.assertTrue((self.state / "split" / "test.sealed").exists())
        again = self.run_eval("--slice", "test")
        self.assertEqual(again.returncode, 2)
        rerun = self.run_eval("--slice", "test", "--rerun-test", "profile rebuilt")
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        rep2 = json.loads((self.state / "rounds" / "test-2" / "report.json").read_text())
        self.assertEqual(rep2["test_runs"], 2)
        self.assertEqual(rep2["rerun_reason"], "profile rebuilt")

    def test_scripted_verdicts_drive_the_report(self):
        test = read_jsonl(self.state / "split" / "test.jsonl")
        ident = {t["id"]: ("correct" if k < 12 else "wrong") for k, t in enumerate(test)}
        r = self.run_eval("--slice", "test", "--stub-script", self.script({"identify": ident, "score_default": 4}))
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertAlmostEqual(rep["id_rate"], 12 / 20)
        self.assertAlmostEqual(rep["mean_rubric"], 4.0)
        self.assertEqual(rep["verdict"], "PASS")

    def test_marker_judge_always_spots_the_stub_and_fails(self):
        r = self.run_eval("--slice", "test", "--stub-script", self.script({"identify_default": "marker"}))
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertEqual(rep["id_rate"], 1.0)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("verdict: FAIL", r.stdout)

    def test_leaky_point_retried_then_excluded_and_copy_excluded(self):
        test = read_jsonl(self.state / "split" / "test.jsonl")
        long_ids = [t["id"] for t in test if len(t["text"].split()) >= 8]
        data = {"extract": {test[0]["id"]: "quote", test[1]["id"]: "quote_once"},
                "generate": {long_ids[-1]: "copy"}}
        self.run_eval("--slice", "test", "--stub-script", self.script(data))
        items = {x["id"]: x for x in read_jsonl(self.state / "rounds" / "test-1" / "items.jsonl")}
        self.assertEqual(items[test[0]["id"]]["excluded"], "point_leak")
        self.assertIsNone(items[test[1]["id"]]["excluded"])
        self.assertEqual(items[test[1]["id"]]["extract_attempts"], 2)
        self.assertEqual(items[long_ids[-1]]["excluded"], "copied")

    def test_context_or_intent_quoting_the_original_is_a_leak(self):
        test = read_jsonl(self.state / "split" / "test.jsonl")
        data = {"extract": {test[0]["id"]: "quote_context", test[1]["id"]: "quote_intent"}}
        self.run_eval("--slice", "test", "--stub-script", self.script(data))
        items = {x["id"]: x for x in read_jsonl(self.state / "rounds" / "test-1" / "items.jsonl")}
        self.assertEqual(items[test[0]["id"]]["excluded"], "point_leak")
        self.assertEqual(items[test[1]["id"]]["excluded"], "point_leak")

    def test_a_broken_runner_does_not_burn_the_seal(self):
        r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--slice", "test", "--runner", "cmd:/nonexistent/runner")
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.state / "split" / "test.sealed").exists())
        r = self.run_eval("--slice", "test", "--stub-script", self.sb.root / "missing.json")
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.state / "split" / "test.sealed").exists())

    def test_test_runs_counts_seal_entries(self):
        self.assertEqual(self.run_eval("--slice", "test").returncode, 0)
        sealed = self.state / "split" / "test.sealed"
        data = json.loads(sealed.read_text())
        data["runs"].append({"round": 99, "reason": "crashed run"})
        sealed.write_text(json.dumps(data))
        self.assertEqual(self.run_eval("--slice", "test", "--rerun-test", "again").returncode, 0)
        rep = json.loads((self.state / "rounds" / "test-2" / "report.json").read_text())
        self.assertEqual(rep["test_runs"], 3)

    def test_non_finite_scores_count_as_zero(self):
        import evaluate
        scores, _ = evaluate.parse_scores('{"voice": {"score": NaN}, "length": {"score": Infinity}, "habit": 4}')
        self.assertEqual((scores["voice"], scores["length"], scores["habit"]), (0.0, 0.0, 4.0))

    def test_judge_sees_train_exemplars_and_random_positions(self):
        self.run_eval("--slice", "test")
        items = read_jsonl(self.state / "rounds" / "test-1" / "items.jsonl")
        train_ids = {t["id"] for t in read_jsonl(self.state / "split" / "train.jsonl")}
        for it in items:
            self.assertTrue(it["exemplars"])
            self.assertTrue(set(it["exemplars"]) <= train_ids)
        self.assertEqual({it["original_pos"] for it in items}, {"A", "B"})

    def test_parallel_jobs_give_the_same_items(self):
        self.assertEqual(self.run_eval("--slice", "test").returncode, 0)
        one = (self.state / "rounds" / "test-1" / "items.jsonl").read_text()
        r = self.run_eval("--slice", "test", "--rerun-test", "jobs check", "--jobs", "6")
        self.assertEqual(r.returncode, 0, r.stderr)
        keys = ("id", "point", "generated", "exemplars", "scores")
        rows1 = [{k: x.get(k) for k in keys} for x in (json.loads(ln) for ln in one.splitlines())]
        rows2 = [{k: x.get(k) for k in keys} for x in read_jsonl(self.state / "rounds" / "test-2" / "items.jsonl")]
        self.assertEqual(rows1, rows2)  # same order and content; positions differ by round on purpose

    def test_invalid_profile_blocks_the_run(self):
        p = self.state / "profile.md"
        p.write_text(p.read_text().replace("## Never", "## Nope"))
        r = self.run_eval("--slice", "test")
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing section", r.stderr)
        self.assertFalse((self.state / "split" / "test.sealed").exists())

    def test_dev_slice_needed_for_revision(self):
        r = self.run_eval("--slice", "dev")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no dev slice", r.stderr)

    def test_weak_judge_is_recorded(self):
        r = self.run_eval("--slice", "test", "--judge-model", "haiku")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertEqual(rep["models"]["judge"], "haiku")
        self.assertTrue(any("judge" in w for w in rep["warnings"]))


class RevisionIsolation(unittest.TestCase):
    """AT-10 on a corpus big enough for a dev slice."""

    def setUp(self):
        self.sb = Sandbox()
        self.state = build_state(self.sb, n=200)

    def tearDown(self):
        self.sb.close()

    def test_feedback_holds_no_held_out_text_and_rounds_are_capped(self):
        dev = read_jsonl(self.state / "split" / "dev.jsonl")
        test = read_jsonl(self.state / "split" / "test.jsonl")
        reasons = {d["id"]: f'sounds off, the original said "{d["text"]}" instead' for d in dev}
        reasons[dev[0]["id"]] = "the generated text misses " + test[0]["text"]
        stub = self.sb.root / "stub.json"
        stub.write_text(json.dumps({"reasons": reasons, "score_default": 2}))
        for k in (1, 2, 3):
            r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--runner", "stub", "--slice", "dev",
                            "--stub-script", stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            fb = (self.state / "rounds" / f"dev-{k}" / "feedback.json").read_text()
            data = json.loads(fb)
            self.assertIn("failed_dims", data)
            canon = mimiclib.canonical(fb)
            for msg in dev + test:
                toks = mimiclib.canonical(msg["text"]).split()
                for j in range(max(1, len(toks) - 3)):
                    span = " ".join(toks[j:j + 4])
                    if len(toks) >= 4:
                        self.assertNotIn(span, canon, msg["id"])
        r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--runner", "stub", "--slice", "dev")
        self.assertEqual(r.returncode, 2)
        self.assertIn("3 rounds", r.stderr)


if __name__ == "__main__":
    unittest.main()
