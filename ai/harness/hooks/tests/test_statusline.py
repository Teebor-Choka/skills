"""Tests for scripts/statusline.py. Run: python3 -m pytest hooks/tests

Statusline stdin fields (https://code.claude.com/docs/en/statusline): session_id, cost.total_cost_usd,
context_window.total_input_tokens, context_window.used_percentage. The script needs no ledger.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "statusline.py")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Statusline(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)

    def run_script(self, payload, raw=None):
        payload = payload if payload is not None else {}
        r = subprocess.run([sys.executable, SCRIPT], input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, timeout=10, env={**os.environ, "HOME": self.home.name})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def plain(self, payload, raw=None):
        return ANSI.sub("", self.run_script(payload, raw)).strip()

    def payload(self, cost=12.34, tokens=450_000, pct=45, session="cur", usage=None):
        cw = {"total_input_tokens": tokens, "used_percentage": pct}
        if usage is not None:
            cw["current_usage"] = usage
        return {"session_id": session, "cost": {"total_cost_usd": cost}, "context_window": cw}

    USAGE = {"input_tokens": 8_000, "output_tokens": 1_200, "cache_creation_input_tokens": 5_000,
             "cache_read_input_tokens": 37_000}  # documented current_usage shape

    def test_e3_context_is_the_current_usage_not_the_cumulative_total(self):
        out = self.plain(self.payload(tokens=450_000, pct=25, usage=self.USAGE))
        self.assertEqual(out, "$12.34 | ctx 50K (25%)")  # 8000 + 5000 + 37000; output tokens excluded
        self.assertNotIn("450K", out)

    def test_e3_percentage_alone_is_still_context(self):
        self.assertEqual(self.plain(self.payload(tokens=450_000, pct=45)), "$12.34 | ctx 45% | total 450K")

    def test_e3_cumulative_only_is_labelled_total_not_ctx(self):
        out = self.plain({"cost": {"total_cost_usd": 1}, "context_window": {"total_input_tokens": 450_000}})
        self.assertEqual(out, "$1.00 | total 450K")
        self.assertNotIn("ctx", out)

    def test_e3_null_current_usage_before_the_first_call(self):
        out = self.plain({"cost": {"total_cost_usd": 0},
                          "context_window": {"total_input_tokens": 0, "used_percentage": None, "current_usage": None}})
        self.assertEqual(out, "$0.00")

    def test_e3_current_usage_with_odd_values_is_ignored_not_fatal(self):
        out = self.plain(self.payload(usage={"input_tokens": "x", "cache_read_input_tokens": None}))
        self.assertNotIn("Traceback", out)
        self.assertIn("$12.34", out)

    def test_works_with_no_ledger_anywhere(self):
        out = self.plain(self.payload())
        self.assertNotIn("today", out)
        self.assertIn("$12.34", out)

    def test_ignores_a_ledger_when_one_exists(self):
        d = os.path.join(self.home.name, ".claude", "metrics")
        os.makedirs(d)
        with open(os.path.join(d, "ledger.jsonl"), "w") as f:
            f.write(json.dumps({"session_id": "o", "ts_last": "2099-01-01T00:00:00Z", "cost_usd": 40.0}) + "\n")
        self.assertEqual(self.plain(self.payload()), "$12.34 | ctx 45% | total 450K")

    def test_context_without_percentage_and_small_token_counts(self):
        self.assertEqual(self.plain({"context_window": {"total_input_tokens": 900}}), "total 900")
        self.assertEqual(self.plain({"cost": {"total_cost_usd": 1}}), "$1.00")

    def test_red_when_cost_reaches_150(self):
        self.assertIn("\x1b[31m", self.run_script(self.payload(cost=150.0, pct=10)))

    def test_red_when_context_reaches_80_percent(self):
        self.assertIn("\x1b[31m", self.run_script(self.payload(cost=1.0, pct=80)))
        self.assertIn("\x1b[31m", self.run_script(self.payload(cost=1.0, pct=80, usage=self.USAGE)))

    def test_not_red_below_limits(self):
        self.assertNotIn("\x1b[31m", self.run_script(self.payload(cost=149.0, pct=79)))

    def test_null_fields_before_the_first_api_call(self):
        out = self.plain({"session_id": "c", "cost": {"total_cost_usd": 0},
                          "context_window": {"total_input_tokens": 0, "used_percentage": None, "current_usage": None}})
        self.assertIn("$0.00", out)

    def test_malformed_input_prints_nothing_harmful(self):
        for raw in ("", "not json", "[]", "{}", '{"cost": 5}'):
            with self.subTest(raw=raw):
                out = self.run_script(None, raw=raw)
                self.assertNotIn("Traceback", out)
                self.assertLess(len(out), 200)

    def test_single_line_output(self):
        self.assertEqual(self.run_script(self.payload()).count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
