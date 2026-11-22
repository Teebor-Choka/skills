"""AT-W8, AT-W9: the budget guard, the ledger, cost-estimate, and the claude JSON reply."""

import json
import sys
import threading
import unittest

from persona_world_fixtures import Sandbox, read_jsonl, split_state
import personalib as m  # noqa: E402


class Ledger(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.path = self.sb.root / "state" / "ledger.jsonl"

    def tearDown(self):
        self.sb.close()

    def test_ledger_sums_and_estimates_from_history(self):
        led = m.Ledger(self.path, call_estimate=0.5)
        run = m.Metered(m.StubRunner({"cost": {"score": 0.02, "predict": 0.1}}), led)
        for _ in range(3):
            run.complete("score", "sonnet", "s", "p" * 100, {})
        run.complete("predict", "opus", "s", "p", {})
        rows = read_jsonl(self.path)
        self.assertEqual([r["role"] for r in rows], ["score"] * 3 + ["predict"])
        self.assertAlmostEqual(led.total(), 0.16)
        self.assertTrue(all(set(r) >= {"ts", "role", "model", "cost_usd", "input_tokens", "output_tokens"}
                            for r in rows))
        self.assertAlmostEqual(led.estimate("score", "sonnet", 100), 0.03)  # 1.5 x the largest seen
        self.assertAlmostEqual(led.estimate("score", "sonnet", 1000), 0.3)  # scaled by prompt length
        self.assertAlmostEqual(led.estimate("update", "opus", 100), 0.5)  # no history: the default

    def test_unknown_cost_is_charged_the_estimate(self):
        led = m.Ledger(self.path, call_estimate=0.4)
        run = m.Metered(m.StubRunner({"cost_unknown": ["update"]}), led)
        run.complete("update", "opus", "s", "p", {})
        run.complete("update", "opus", "s", "p", {})
        rows = read_jsonl(self.path)
        self.assertEqual([r["cost_usd"] for r in rows], [0.4, 0.4])
        self.assertTrue(all(r["estimated"] for r in rows))

    def test_guard_refuses_before_the_cap(self):
        led = m.Ledger(self.path, max_cost=0.1, call_estimate=0.03)
        run = m.Metered(m.StubRunner({"cost_default": 0.03}), led)
        done = 0
        with self.assertRaises(m.BudgetExceeded) as e:
            for _ in range(10):
                run.complete("score", "sonnet", "s", "p", {})
                done += 1
        self.assertEqual(e.exception.code, 4)
        self.assertEqual(done, 2)  # a third would cost 0.06 + 0.045 > 0.1
        self.assertLessEqual(led.total(), 0.1)

    def test_parallel_reservations_cannot_overshoot(self):
        led = m.Ledger(self.path, max_cost=1.0, call_estimate=0.3)
        ok, refused, gate = [], [], threading.Barrier(6)

        def worker():
            gate.wait()
            try:
                ok.append(led.reserve("score", "sonnet", 10))
            except m.BudgetExceeded:
                refused.append(1)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual((len(ok), len(refused)), (3, 3))


class ClaudeReply(unittest.TestCase):
    def test_argv_asks_for_json(self):
        argv = m.claude_argv("opus", "SYS")
        i = argv.index("--output-format")
        self.assertEqual(argv[i + 1], "json")

    def test_result_cost_and_tokens_are_parsed(self):
        out = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "hello there",
                          "total_cost_usd": 0.0123, "usage": {"input_tokens": 10, "output_tokens": 5,
                                                              "cache_creation_input_tokens": 100,
                                                              "cache_read_input_tokens": 1000}})
        text, usage = m.parse_cli_reply(out)
        self.assertEqual(text, "hello there")
        self.assertEqual(usage, {"cost_usd": 0.0123, "input_tokens": 1110, "output_tokens": 5})

    def test_error_reply_is_a_failure(self):
        for obj in ({"is_error": True, "result": "boom", "subtype": "success"},
                    {"is_error": False, "result": "x", "subtype": "error_max_turns"}):
            with self.assertRaises(m.RunnerError):
                m.parse_cli_reply(json.dumps(obj))

    def test_plain_text_has_unknown_cost(self):
        self.assertEqual(m.parse_cli_reply("just text"), ("just text", {"cost_usd": None, "input_tokens": None,
                                                                        "output_tokens": None}))

    def test_cmd_runner_reads_the_json_reply(self):
        sb = Sandbox()
        try:
            script = sb.root / "fake.py"
            script.write_text("import json, sys\nsys.stdin.read()\nprint(json.dumps({'type': 'result', "
                              "'subtype': 'success', 'is_error': False, 'result': 'ok', 'total_cost_usd': 0.25, "
                              "'usage': {'input_tokens': 3, 'output_tokens': 4}}))\n")
            r = m.CommandRunner(f"cmd:{sys.executable} {script}")
            self.assertEqual(r.invoke("score", "sonnet", "s", "p", {}),
                             ("ok", {"cost_usd": 0.25, "input_tokens": 3, "output_tokens": 4, "prior": []}))
        finally:
            sb.close()

    def test_claude_runner_refuses_a_reply_that_is_not_the_json_object(self):
        env = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "x",
                          "total_cost_usd": 0.1})
        for out in ("Warning: something\n" + env, "[1, 2]", "plain words"):
            with self.subTest(out=out[:20]), self.assertRaises(m.RunnerError):
                m.parse_cli_reply(out, strict=True)

    def test_every_paid_attempt_is_charged(self):
        sb = Sandbox()
        try:
            flag = sb.root / "first"
            script = sb.root / "flaky.py"
            script.write_text(
                "import json, os, sys\nsys.stdin.read()\nflag = sys.argv[1]\n"
                "first = not os.path.exists(flag)\nopen(flag, 'w').close()\n"
                "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': first, "
                "'result': 'boom' if first else 'ok', 'total_cost_usd': 0.3}))\n")
            led = m.Ledger(sb.root / "ledger.jsonl", max_cost=10)
            run = m.Metered(m.CommandRunner(f"cmd:{sys.executable} {script} {flag}"), led)
            self.assertEqual(run.complete("score", "sonnet", "s", "p", {}), "ok")
            self.assertAlmostEqual(led.total(), 0.6)
            self.assertEqual(len(read_jsonl(sb.root / "ledger.jsonl")), 2)
            # both attempts failing: both are charged too
            bad = sb.root / "bad.py"
            bad.write_text("import json, sys\nsys.stdin.read()\nprint(json.dumps({'is_error': True, "
                           "'result': 'no', 'total_cost_usd': 0.2}))\n")
            run = m.Metered(m.CommandRunner(f"cmd:{sys.executable} {bad}"), led)
            with self.assertRaises(m.RunnerError):
                run.complete("score", "sonnet", "s", "p", {})
            self.assertAlmostEqual(led.total(), 1.0)
        finally:
            sb.close()

    def test_a_command_runner_call_reserves_both_attempts(self):
        sb = Sandbox()
        try:
            led = m.Ledger(sb.root / "ledger.jsonl", max_cost=0.9, call_estimate=0.5)
            run = m.Metered(m.CommandRunner(f"cmd:{sys.executable} -c pass"), led)
            with self.assertRaises(m.BudgetExceeded):
                run.complete("score", "sonnet", "s", "p", {})  # 2 x 0.5 > 0.9, refused before running
            self.assertFalse((sb.root / "ledger.jsonl").exists())
        finally:
            sb.close()


class WorldBudget(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        split_state(self.sb, n=40)
        self.d = self.sb.state("pat")
        self.script = self.sb.root / "stub.json"
        self.script.write_text(json.dumps({"cost_default": 0.01, "score_default": 1}))
        r = self.sb.run("world.py", "init", "--persona", "pat")
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self.sb.close()

    def world(self, *args):
        return self.sb.run("world.py", args[0], "--persona", "pat", "--runner", "stub",
                           "--stub-script", self.script, *args[1:])

    def test_run_stops_with_exit_4_and_keeps_the_last_checkpoint(self):
        r = self.world("run", "--max-cost-usd", "0.2", "--call-estimate-usd", "0.02")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("budget", r.stderr)
        rows = read_jsonl(self.d / "ledger.jsonl")
        total = sum(x["cost_usd"] for x in rows)
        self.assertAlmostEqual(total, 0.01 * len(rows))
        self.assertLessEqual(total, 0.2 + 1e-9)
        st = json.loads((self.d / "state.json").read_text())
        self.assertGreater(st["next"], 0)
        self.assertEqual(len(read_jsonl(self.d / "log.jsonl")), st["next"])
        r = self.world("run", "--resume", "--max-cost-usd", "100")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_final_preflight_refuses_before_the_seal(self):
        self.assertEqual(self.world("run").returncode, 0)
        r = self.world("final", "--max-cost-usd", "0.01")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertFalse((self.d / "split" / "test.sealed").exists())

    def test_evaluate_preflight_refuses_before_the_seal(self):
        r = self.sb.run("profile.py", "skeleton", "--persona", "pat")
        self.assertEqual(r.returncode, 0, r.stderr)
        from persona_fixtures import fill_profile
        p = self.d / "profile.md"
        p.write_text(fill_profile(p.read_text()))
        r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--slice", "test", "--runner", "stub",
                        "--max-cost-usd", "0.01")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertFalse((self.d / "split" / "test.sealed").exists())
        r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--slice", "test", "--runner", "stub")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(read_jsonl(self.d / "ledger.jsonl"))  # evaluate logs to the same ledger

    def test_budget_stop_inside_the_final_does_not_use_up_the_slice(self):
        self.assertEqual(self.world("run").returncode, 0)
        # the preflight passes on history; the generator then costs far more than ever seen
        self.script.write_text(json.dumps({"cost_default": 0.01, "score_default": 1, "cost": {"generate": 5.0}}))
        r = self.world("final", "--max-cost-usd", "20", "--call-estimate-usd", "0.01")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("not used up", r.stderr)
        seal = json.loads((self.d / "split" / "test.sealed").read_text())
        self.assertEqual(seal["runs"][-1]["aborted"], "budget")
        self.script.write_text(json.dumps({"cost_default": 0.01, "score_default": 1}))
        r = self.world("final")  # no --rerun-test needed: nothing was reported
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.world("final").returncode, 2)

    def test_ledger_counts_another_process_spend(self):
        led = m.Ledger(self.d / "ledger.jsonl", max_cost=1.0, call_estimate=0.1)
        other = m.Ledger(self.d / "ledger.jsonl")
        m.Metered(m.StubRunner({"cost_default": 0.95}), other).complete("score", "x", "s", "p", {})
        with self.assertRaises(m.BudgetExceeded):
            led.reserve("score", "y", 1)

    def test_final_preflight_scales_the_loops_costs_to_a_stronger_tier(self):
        self.assertEqual(self.world("run").returncode, 0)
        spent = sum(x["cost_usd"] for x in read_jsonl(self.d / "ledger.jsonl"))
        # the roles the final adds (generate, and identify and score on the stronger judge) have no
        # history: the flat default (0.5 x 2 attempts each, about $50) would not fit this cap
        r = self.world("final", "--max-cost-usd", str(spent + 15))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.d / "split" / "test.sealed").exists())

    def test_final_preflight_still_refuses_a_real_projection_over_the_cap(self):
        self.assertEqual(self.world("run").returncode, 0)
        spent = sum(x["cost_usd"] for x in read_jsonl(self.d / "ledger.jsonl"))
        r = self.world("final", "--max-cost-usd", str(spent + 0.5))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("the sealed slice is untouched", r.stderr)
        self.assertFalse((self.d / "split" / "test.sealed").exists())

    def test_status_reports_measured_and_estimated_cost_apart(self):
        self.script.write_text(json.dumps({"cost_default": 0.01, "score_default": 1, "cost_unknown": ["update"]}))
        self.assertEqual(self.world("run", "--max-steps", "3", "--call-estimate-usd", "0.05").returncode, 0)
        cost = json.loads(self.world("status").stdout)["cost"]
        self.assertIn("measured", cost)
        self.assertIn("estimated", cost)
        rows = read_jsonl(self.d / "ledger.jsonl")
        self.assertAlmostEqual(cost["estimated"], sum(x["cost_usd"] for x in rows if x["estimated"]))
        self.assertAlmostEqual(cost["measured"], sum(x["cost_usd"] for x in rows if not x["estimated"]))
        self.assertGreater(cost["estimated"], 0)
        self.assertAlmostEqual(cost["measured"] + cost["estimated"], cost["total"])

    def test_cap_basis_measured_ignores_estimated_rows(self):
        self.script.write_text(json.dumps({"cost_default": 0.01, "score_default": 1, "cost_unknown": ["update"]}))
        flags = ("--max-steps", "20", "--max-cost-usd", "0.5", "--call-estimate-usd", "0.05")
        self.assertEqual(self.world("run", *flags).returncode, 4)  # default: measured + estimated
        both = json.loads((self.d / "state.json").read_text())["next"]
        self.assertEqual(self.world("run", "--resume", *flags).returncode, 4)  # the same cap, no room left
        self.assertEqual(json.loads((self.d / "state.json").read_text())["next"], both)
        r = self.world("run", "--resume", *flags, "--cap-basis", "measured")
        self.assertIn(r.returncode, (0, 4), r.stderr)
        self.assertGreater(json.loads((self.d / "state.json").read_text())["next"], both)

    def test_cost_estimate_runs_n_steps_and_projects(self):
        r = self.world("cost-estimate", "--steps", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        est = json.loads(r.stdout)
        n = len(json.loads((self.d / "stream.json").read_text())["ids"])
        self.assertEqual(est["steps_run"], 5)
        self.assertEqual(est["stream_steps"], n)
        self.assertGreater(est["per_step_mean"], 0)
        self.assertAlmostEqual(est["projected_loop_total"],
                               est["spent_loop"] + est["per_step_mean"] * (n - 5), places=6)
        self.assertIn("projected_final", est)
        self.assertEqual(json.loads((self.d / "state.json").read_text())["next"], 5)
        self.assertEqual(self.world("run", "--resume").returncode, 0)


if __name__ == "__main__":
    unittest.main()
