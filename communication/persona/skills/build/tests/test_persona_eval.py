"""AT-7 to AT-13: judge order, report math, verdict, revision isolation, leak checks, runners, end to end."""

import json
import unittest
from collections import Counter

from persona_fixtures import Sandbox, build_state, read_jsonl
import personalib  # noqa: E402  (path set by persona_fixtures)

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
        a = [personalib.original_first(1337, 1, i) for i in ids]
        self.assertEqual(a, [personalib.original_first(1337, 1, i) for i in ids])
        self.assertNotEqual(a, [personalib.original_first(1338, 1, i) for i in ids])
        self.assertNotEqual(a, [personalib.original_first(1337, 2, i) for i in ids])
        self.assertTrue(160 < sum(a) < 240, sum(a))

    def test_always_a_judge_is_invalid(self):
        items = [item(i, identified=(i % 2 == 0), picked="A") for i in range(30)]
        s = personalib.summarize(items)
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
        s = personalib.summarize(items)
        self.assertEqual(s["n_scored"], 20)
        self.assertAlmostEqual(s["id_rate"], 10 / 20)  # item 3 was already among the first 10
        self.assertAlmostEqual(s["dims"]["voice"], (1 + 0 + 4 * 18) / 20)
        self.assertAlmostEqual(s["mean_rubric"], (1 + 0 + 4 * 18) / 20)
        self.assertEqual(s["by_band"]["long"]["n"], 1)
        self.assertEqual(s["by_channel"]["email"]["n"], 1)
        self.assertEqual(s["by_band"]["short"]["n"], 19)
        self.assertEqual(s["worst"][:2], ["i002", "i000"])
        self.assertEqual(s["unparseable"], {"identify": 1, "score": 1})

    def test_unparseable_pick_counts_against_the_persona(self):
        items = balanced(20, 0)
        for it in items[:5]:
            it["identified"], it["picked"] = None, None
        self.assertAlmostEqual(personalib.summarize(items)["id_rate"], 5 / 20)

    def test_excluded_items_are_not_scored(self):
        items = balanced(20, 10) + [item(99, excluded="point_leak")]
        s = personalib.summarize(items)
        self.assertEqual((s["n_total"], s["n_scored"]), (21, 20))
        self.assertEqual(s["excluded"], {"point_leak": 1})

    def test_short_exact_match_rate_is_reported_but_not_judged(self):
        items = balanced(20, 10)
        for k, it in enumerate(items[:8]):
            it["original"] = "Ship it."
            it["generated"] = "ship it" if k < 2 else "Send it over."
        items[8]["band"] = "long"
        items[8]["original"] = items[8]["generated"] = "same long text here"
        s = personalib.summarize(items)
        self.assertEqual(s["short_exact_match"], {"n": 8, "matches": 2, "rate": 0.25})
        self.assertEqual(s["verdict"], personalib.summarize(balanced(20, 10))["verdict"])


class Verdict(unittest.TestCase):
    def test_pass_at_the_thresholds(self):
        self.assertEqual(personalib.summarize(balanced(20, 13, scores=3.5))["verdict"], "PASS")

    def test_fail_just_above_id_rate(self):
        self.assertEqual(personalib.summarize(balanced(20, 14))["verdict"], "FAIL")

    def test_fail_on_rubric(self):
        s = personalib.summarize(balanced(20, 10, scores=3))
        self.assertEqual(s["verdict"], "FAIL")
        self.assertEqual(s["failed_dims"], [])  # 3.0 is at the floor, not below
        self.assertEqual(personalib.summarize(balanced(20, 10, scores=2))["failed_dims"], DIMS)

    def test_inconclusive_below_min_n(self):
        self.assertEqual(personalib.summarize(balanced(19, 9))["verdict"], "INCONCLUSIVE")

    def test_invalid_when_too_many_excluded(self):
        items = balanced(20, 10) + [item(100 + i, excluded="copied") for i in range(6)]
        self.assertEqual(personalib.summarize(items)["verdict"], "INVALID")

    def test_thresholds_are_configurable(self):
        t = dict(personalib.THRESHOLDS, max_id_rate=0.75, min_n=10)
        self.assertEqual(personalib.summarize(balanced(12, 9), t)["verdict"], "PASS")

    def test_caricature_fails(self):
        # A judge that reliably picks the generated one can tell them apart: two-sided band.
        s = personalib.summarize(balanced(20, 6))
        self.assertEqual(s["verdict"], "FAIL")
        self.assertTrue(any("caricature" in w for w in s["warnings"]))
        self.assertEqual(personalib.summarize(balanced(20, 7))["verdict"], "PASS")


class LeakChecks(unittest.TestCase):
    def test_emoji_only_messages_have_their_own_key_and_leak_check(self):
        self.assertLess(personalib.similarity("👍", "😂"), 0.7)
        self.assertEqual(personalib.similarity("👍", "👍 "), 1.0)
        self.assertEqual(len(set(personalib.near_dup_clusters(["👍", "😂", "🔥", "..."]))), 4)
        self.assertTrue(personalib.point_leaks("reacts with 👍", "👍"))
        self.assertFalse(personalib.point_leaks("reacts with approval", "👍"))

    def test_point_leak_rules(self):
        orig = "can we push the staging db fix to friday please"
        self.assertTrue(personalib.point_leaks("asks to push the staging db fix later", orig))
        self.assertFalse(personalib.point_leaks("asks to delay a database repair by some days", orig))
        self.assertTrue(personalib.point_leaks("replies sgtm to the plan", "sgtm"))
        self.assertFalse(personalib.point_leaks("agrees with the plan", "sgtm"))

    def test_copied_rule_only_for_long_originals(self):
        long = "I went through the budget this morning and the numbers hold up fine"
        self.assertTrue(personalib.copied(long + "!", long))
        self.assertFalse(personalib.copied("ok", "ok"))

    def test_sanitize_drops_quotes_and_held_out_spans(self):
        held = ["we are two days behind because the supplier changed"]
        reasons = [
            'too formal; the original said "two days behind" bluntly',
            "missing the two days behind because tone",
            "length right, opener wrong",
        ]
        out = personalib.sanitize_reasons(reasons, held)
        self.assertEqual(out, ["too formal; the original said bluntly", "length right, opener wrong"])


class Runners(unittest.TestCase):
    def test_claude_argv_is_isolated(self):
        argv = personalib.claude_argv("opus", "SYS")
        self.assertEqual(argv, ["claude", "-p", "--model", "opus", "--no-session-persistence", "--tools", "",
                                "--strict-mcp-config", "--setting-sources", "", "--system-prompt", "SYS"])

    def test_tier_resolution(self):
        self.assertEqual(personalib.resolve_model("reasoning", {}), ("opus", "reasoning"))
        self.assertEqual(personalib.resolve_model("haiku", {}), ("haiku", "light"))
        self.assertEqual(personalib.resolve_model("claude-x-1", {}), ("claude-x-1", None))

    def test_tiers_file_override(self):
        sb = Sandbox()
        try:
            f = sb.root / "tiers.json"
            f.write_text(json.dumps({"tiers": {"reasoning": {"claude": "fable", "codex": "TODO"},
                                               "execution": {"codex": "TODO"}}}))
            env = {"AGENT_TIERS_FILE": str(f)}
            self.assertEqual(personalib.resolve_model("reasoning", env), ("fable", "reasoning"))
            self.assertEqual(personalib.resolve_model("execution", env), ("sonnet", "execution"))
            self.assertEqual(personalib.resolve_model("reasoning", dict(env, AGENT_HARNESS="codex")), ("opus", "reasoning"))
        finally:
            sb.close()

    def test_default_roles_use_the_strongest_tier_for_judge_and_generator(self):
        self.assertEqual(personalib.ROLE_TIERS["judge"], "reasoning")
        self.assertEqual(personalib.ROLE_TIERS["generate"], "reasoning")


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

    def test_folds_needed_for_revision(self):
        r = self.run_eval("--slice", "dev")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no folds", r.stderr)

    def test_weak_judge_is_recorded(self):
        r = self.run_eval("--slice", "test", "--judge-model", "haiku")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertEqual(rep["models"]["judge"], "haiku")
        self.assertTrue(any("judge" in w for w in rep["warnings"]))


class RevisionIsolation(unittest.TestCase):
    """AT-10 on a corpus big enough for folds."""

    def setUp(self):
        self.sb = Sandbox()
        self.state = build_state(self.sb, n=200)

    def tearDown(self):
        self.sb.close()

    def test_feedback_holds_no_held_out_text(self):
        train = read_jsonl(self.state / "split" / "train.jsonl")
        test = read_jsonl(self.state / "split" / "test.jsonl")
        reasons = {t["id"]: f'sounds off, the original said "{t["text"]}" instead' for t in train}
        first = next(t for t in train if t["fold"] == 0)
        reasons[first["id"]] = "the generated text misses " + test[0]["text"]
        stub = self.sb.root / "stub.json"
        stub.write_text(json.dumps({"reasons": reasons, "score_default": 2}))
        for k in (1, 2, 3):
            r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--runner", "stub", "--slice", "dev",
                            "--stub-script", stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            fb = (self.state / "rounds" / f"dev-{k}" / "feedback.json").read_text()
            data = json.loads(fb)
            self.assertIn("failed_dims", data)
            self.assertIn("by_band", data)
            canon = personalib.canonical(fb)
            for msg in [t for t in train if t["fold"] == k - 1] + test:
                toks = personalib.canonical(msg["text"]).split()
                for j in range(max(1, len(toks) - 3)):
                    span = " ".join(toks[j:j + 4])
                    if len(toks) >= 4:
                        self.assertNotIn(span, canon, msg["id"])



def rnd(k, short, long, rub=4.0, n_short=40, n_long=10, fold=None):
    """A scripted dev round: per-band (id rate, rubric)."""
    rs, rl = (rub, rub) if not isinstance(rub, tuple) else rub
    return {"round": k, "fold": fold, "profile_hash": f"h{k}",
            "by_band": {"short": {"n": n_short, "id_rate": short, "mean_rubric": rs},
                        "long": {"n": n_long, "id_rate": long, "mean_rubric": rl}}}


class GroupVerdicts(unittest.TestCase):
    def test_each_channel_and_band_gets_its_own_verdict_and_the_overall_one_is_unchanged(self):
        chat = [item(i, identified=i < 10, picked="AB"[i % 2], channel="chat") for i in range(20)]
        mail = [item(100 + i, identified=True, picked="AB"[i % 2], channel="email", band="long") for i in range(20)]
        few = [item(200 + i, identified=i < 2, picked="AB"[i % 2], channel="sms") for i in range(5)]
        s = personalib.summarize(chat + mail + few)
        self.assertEqual(s["by_channel"]["chat"]["verdict"], "PASS")
        self.assertEqual(s["by_channel"]["email"]["verdict"], "FAIL")
        self.assertEqual(s["by_channel"]["sms"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(s["by_band"]["long"]["verdict"], "FAIL")
        self.assertEqual(s["verdict"], "FAIL")  # 32 of 45: overall rule as before
        self.assertAlmostEqual(s["id_rate"], 32 / 45, places=4)

    def test_a_channel_with_too_many_exclusions_is_invalid(self):
        chat = balanced(20, 10) + [item(300 + i, excluded="copied") for i in range(6)]
        mail = [item(100 + i, identified=i < 20, picked="AB"[i % 2], channel="email") for i in range(40)]
        s = personalib.summarize(chat + mail)
        self.assertEqual(s["by_channel"]["chat"]["verdict"], "INVALID")
        self.assertEqual(s["by_channel"]["email"]["verdict"], "PASS")
        self.assertEqual(s["verdict"], "PASS")  # 6 of 66 excluded overall

    def test_report_table_shows_group_verdicts(self):
        import evaluate
        s = personalib.summarize(balanced(20, 10))
        s.update(persona="pat", slice="test", round=1, models={"judge": "opus"}, runner="stub")
        self.assertIn("| channel: chat | 20 | 0.50 | 4.00 | PASS |", evaluate.report_md(s))


class Selection(unittest.TestCase):
    """The best-round rule: worst band closest to 0.5, rubric floor per band, noise margin, latest."""

    def test_picks_the_round_whose_worst_band_is_closest_to_half(self):
        rounds = [rnd(1, 0.5, 1.0, n_long=40), rnd(2, 0.55, 0.5, n_long=40), rnd(3, 0.3, 0.6, n_long=40)]
        sel = personalib.select_round(rounds, 3.5)
        self.assertEqual(sel["round"], 2)
        self.assertTrue(sel["floor_met"])
        self.assertAlmostEqual(sel["margin"], (0.25 / 40) ** 0.5, places=4)

    def test_rubric_floor_applies_per_band(self):
        rounds = [rnd(1, 0.5, 0.5, rub=(4.0, 3.4)), rnd(2, 0.7, 0.9)]
        self.assertEqual(personalib.select_round(rounds, 3.5)["round"], 2)

    def test_within_the_noise_margin_the_latest_round_wins(self):
        # long n=10: margin 0.158; round 3 is 0.10 worse than round 1, within noise
        rounds = [rnd(1, 0.5, 0.5), rnd(2, 0.5, 0.9), rnd(3, 0.6, 0.4)]
        sel = personalib.select_round(rounds, 3.5)
        self.assertEqual(sel["round"], 3)
        self.assertEqual(sel["tie_set"], [1, 3])
        # outside the margin the closer round holds
        rounds[2] = rnd(3, 0.5, 0.75, n_long=40, n_short=40)
        rounds[0] = rnd(1, 0.5, 0.5, n_long=40, n_short=40)
        self.assertEqual(personalib.select_round(rounds, 3.5)["round"], 1)

    def test_exact_tie_takes_the_latest(self):
        self.assertEqual(personalib.select_round([rnd(1, 0.6, 0.6), rnd(2, 0.4, 0.4)], 3.5)["round"], 2)

    def test_no_round_meets_the_floor(self):
        rounds = [rnd(1, 0.5, 0.5, rub=3.0), rnd(2, 0.9, 0.9, rub=(3.4, 3.2)), rnd(3, 0.5, 0.5, rub=(3.2, 3.6))]
        sel = personalib.select_round(rounds, 3.5)
        self.assertFalse(sel["floor_met"])
        self.assertEqual(sel["round"], 3)  # highest worst-band rubric (3.2), latest of the tie

    def test_no_rounds(self):
        with self.assertRaises(personalib.Fail):
            personalib.select_round([], 3.5)


class StopRule(unittest.TestCase):
    def test_converges_when_both_bands_pass_twice_and_hold_steady(self):
        rounds = [rnd(1, 0.5, 0.9), rnd(2, 0.5, 0.6), rnd(3, 0.55, 0.5)]
        self.assertEqual(personalib.stop_rule(rounds)[0], "converged")
        self.assertIsNone(personalib.stop_rule(rounds[:2])[0])

    def test_no_convergence_when_a_band_moves_more_than_its_se(self):
        rounds = [rnd(1, 0.5, 0.36, n_long=40), rnd(2, 0.5, 0.64, n_long=40)]  # 0.28 > se 0.079
        self.assertIsNone(personalib.stop_rule(rounds)[0])

    def test_no_convergence_below_the_rubric_floor(self):
        rounds = [rnd(1, 0.5, 0.5, rub=(4.0, 3.0)), rnd(2, 0.5, 0.5, rub=(4.0, 3.0))]
        self.assertIsNone(personalib.stop_rule(rounds)[0])

    def test_plateau_after_three_rounds_without_improvement(self):
        base = [rnd(1, 0.5, 1.0, n_long=40), rnd(2, 0.5, 0.8, n_long=40)]
        flat = [rnd(3, 0.5, 0.85, n_long=40), rnd(4, 0.5, 0.75, n_long=40), rnd(5, 0.5, 0.9, n_long=40)]
        self.assertEqual(personalib.stop_rule(base + flat)[0], "plateau")
        better = flat[:2] + [rnd(5, 0.5, 0.65, n_long=40)]  # 0.15 better than 0.8: beyond se 0.079
        self.assertIsNone(personalib.stop_rule(base + better)[0])
        self.assertIsNone(personalib.stop_rule(base + flat[:2])[0])

    def test_cap(self):
        # long improves by 0.02 a round (beyond se 0.016 at n 1000) but never enters the band
        rounds = [rnd(k, 0.5, 1.01 - 0.02 * k, n_long=1000) for k in range(1, 11)]
        self.assertIsNone(personalib.stop_rule(rounds[:9], max_rounds=10)[0])
        self.assertEqual(personalib.stop_rule(rounds, max_rounds=10)[0], "cap")


class Folds(unittest.TestCase):
    """k-fold revision over TRAIN, the profile snapshot per round, and the recorded selection."""

    def setUp(self):
        self.sb = Sandbox()
        self.state = build_state(self.sb, n=200)
        self.train = read_jsonl(self.state / "split" / "train.jsonl")

    def tearDown(self):
        self.sb.close()

    def run_eval(self, *args):
        return self.sb.run("evaluate.py", "run", "--persona", "pat", "--runner", "stub", *args)

    def select(self):
        return self.sb.run("evaluate.py", "select", "--persona", "pat")

    def test_dev_rounds_rotate_folds_and_snapshot_the_profile(self):
        prof = self.state / "profile.md"
        self.assertEqual(self.run_eval("--slice", "dev").returncode, 0)
        self.assertEqual(self.run_eval("--slice", "dev").returncode, 0)
        prof.write_text(prof.read_text() + "\nOne more rule.\n")
        r = self.run_eval("--slice", "dev")
        self.assertEqual(r.returncode, 0, r.stderr)
        examples = personalib.example_ids(prof.read_text())
        self.assertTrue(examples)
        for k in (1, 2, 3):
            out = self.state / "rounds" / f"dev-{k}"
            rep = json.loads((out / "report.json").read_text())
            self.assertEqual(rep["fold"], k - 1)
            fold_ids = {t["id"] for t in self.train if t["fold"] == k - 1} - examples
            items = read_jsonl(out / "items.jsonl")
            self.assertEqual({x["id"] for x in items}, fold_ids)
            for x in items:
                self.assertFalse(set(x["exemplars"]) & fold_ids)
            self.assertTrue((out / "profile.md").exists())
        self.assertEqual((self.state / "rounds" / "dev-3" / "profile.md").read_text(), prof.read_text())
        revised = [json.loads((self.state / "rounds" / f"dev-{k}" / "report.json").read_text())["revised"]
                   for k in (1, 2, 3)]
        self.assertEqual(revised, [None, False, True])

    def test_a_profile_quoting_the_round_fold_is_refused(self):
        prof = self.state / "profile.md"
        examples = personalib.example_ids(prof.read_text())
        quote = next(t for t in self.train if t["fold"] == 0 and len(t["text"].split()) >= 8
                     and t["id"] not in examples)
        prof.write_text(prof.read_text().replace("## Lexicon\n", "## Lexicon\n\n" + quote["text"] + "\n", 1))
        r = self.run_eval("--slice", "dev")
        self.assertEqual(r.returncode, 2)
        self.assertIn("held-out", r.stderr)
        self.assertFalse((self.state / "rounds" / "dev-1").exists())

    def test_the_sealed_test_needs_a_recorded_selection_and_uses_its_profile(self):
        self.assertEqual(self.select().returncode, 2)  # no dev rounds yet
        self.assertEqual(self.run_eval("--slice", "dev").returncode, 0)
        r = self.run_eval("--slice", "test")
        self.assertEqual(r.returncode, 2)
        self.assertIn("select", r.stderr)
        self.assertFalse((self.state / "split" / "test.sealed").exists())
        r = self.select()
        self.assertEqual(r.returncode, 0, r.stderr)
        sel = json.loads((self.state / "rounds" / "selection.json").read_text())
        self.assertEqual(sel["round"], 1)
        self.assertIn("rule", sel)
        prof = self.state / "profile.md"
        prof.write_text(prof.read_text() + "\nA later edit that was never judged.\n")
        r = self.run_eval("--slice", "test")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((self.state / "rounds" / "test-1" / "report.json").read_text())
        self.assertEqual(rep["profile_hash"], sel["profile_hash"])
        self.assertEqual(rep["selected_round"], 1)
        self.assertEqual(self.select().returncode, 2)  # sealed: the choice is final

    def test_a_tampered_snapshot_is_refused(self):
        self.assertEqual(self.run_eval("--slice", "dev").returncode, 0)
        self.assertEqual(self.select().returncode, 0)
        snap = self.state / "rounds" / "dev-1" / "profile.md"
        snap.write_text(snap.read_text() + "\nedited\n")
        r = self.run_eval("--slice", "test")
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.state / "split" / "test.sealed").exists())

    def test_a_converged_loop_refuses_more_rounds(self):
        order = sorted(self.train, key=lambda t: (t["fold"], t["band"], t["id"]))  # half right per fold and band
        ident = {t["id"]: ("correct" if k % 2 else "wrong") for k, t in enumerate(order)}
        stub = self.sb.root / "stub.json"
        stub.write_text(json.dumps({"identify": ident, "score_default": 4}))
        for _ in (1, 2):
            r = self.run_eval("--slice", "dev", "--stub-script", stub)
            self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((self.state / "rounds" / "dev-2" / "report.json").read_text())
        self.assertEqual(rep["stop"], "converged")
        r = self.run_eval("--slice", "dev", "--stub-script", stub)
        self.assertEqual(r.returncode, 2)
        self.assertIn("converged", r.stderr)


if __name__ == "__main__":
    unittest.main()
