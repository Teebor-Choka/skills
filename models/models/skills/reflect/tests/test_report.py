"""report.py: weekly report, before/after comparison, north star, alerts (IM-43, IM-61, IM-32, IM-26)."""
import json
import pathlib

import pytest

from helpers import run_script

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
TRANSCRIPTS = [FIX / f"{n}.jsonl" for n in ("compaction", "swarm", "unknown-model", "pr-repeats")]
WINDOW = ["--until", "2026-03-08", "--days", "7"]


def report(tmp_path, *extra, transcripts=True, outcomes=FIX / "pr-outcomes.jsonl"):
    out = tmp_path / "report.json"
    args = [*(TRANSCRIPTS if transcripts else []), "--records", FIX / "records-prior.jsonl",
            "--outcomes", outcomes, *WINDOW, "--json", out, *extra]
    r = run_script("report.py", *args)
    return r, (json.loads(out.read_text()) if out.exists() else None)


def test_golden_table(tmp_path):
    r, _ = report(tmp_path, "--changes", FIX / "changes.jsonl")
    assert (FIX / "golden.txt").read_text() == r.stdout


def test_north_star_is_cost_over_merged_prs_with_its_three_companions(tmp_path):
    _, rep = report(tmp_path)
    ns = rep["north_star"]
    assert ns["cost_per_merged_pr"] == pytest.approx(18.0)  # one session, $18, one PR merged
    assert ns["prs"] == 3 and ns["merged"] == 1
    assert ns["merged_share"] == pytest.approx(1 / 3)
    assert ns["hours_to_merge_p50"] == 12.0 and ns["review_rounds_p50"] == 1


def test_north_star_is_withheld_without_the_companions(tmp_path):
    bare = tmp_path / "bare.jsonl"
    bare.write_text('{"ref":"o/r#7","state":"MERGED","merged":"2026-03-06T20:00:00Z"}\n')
    r, rep = report(tmp_path, outcomes=bare)
    assert "withheld" in r.stdout and "cost per merged PR: $" not in r.stdout
    assert rep["north_star"]["cost_per_merged_pr"] is None


def test_metric_values_of_the_fixture_week(tmp_path):
    _, rep = report(tmp_path)
    m = rep["metrics"]
    assert m["m1"]["value"] == pytest.approx(20.5015 / 7)   # priced sessions only
    assert m["m2"]["value"] == pytest.approx(40.0)          # 2 errors in 5 calls
    assert m["m3"]["value"] == pytest.approx(80.0) and m["m3"]["repeat_ratio"] == 0.5
    assert m["m4"]["value"] == 1
    assert m["m5"]["value"] == pytest.approx(25.0)          # (1 interrupt + 1 nudge) / 8 prompts
    assert m["m6"]["p50"] == 0 and m["m6"]["p90"] == pytest.approx(8870 / 9010, abs=1e-3)
    assert m["m10"]["value"] == pytest.approx(0.25)         # 1 compaction over 4 sessions
    assert m["m11"]["value"] == pytest.approx(2 / 13)
    assert m["m12"]["value"] == 1


def test_before_column_comes_from_the_previous_window(tmp_path):
    _, rep = report(tmp_path)
    assert rep["metrics"]["m1"]["before"] == pytest.approx(1.5)
    assert rep["metrics"]["m2"]["before"] == pytest.approx(3.0)
    assert rep["metrics"]["m4"]["before"] == 0


def test_alerts_fire_and_exit_code_is_one(tmp_path):
    r, rep = report(tmp_path)
    assert r.returncode == 1
    fired = {a["metric"] for a in rep["alerts"]}
    assert {"m1", "m3", "m4", "m5", "m6", "m11", "m12", "north_star"} <= fired


def test_a_clean_week_exits_zero(tmp_path):
    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps({"session_id": "c", "ts_last": "2026-03-05T10:00:00Z",
                                 "project": "p", "turns": 10, "human_prompts": 10,
                                 "cost_usd": 5.0, "tool_calls": 100, "tool_errors": 1,
                                 "wall_seconds": 600}) + "\n")
    out = tmp_path / "r.json"
    r = run_script("report.py", "--records", clean, *WINDOW, "--json", out)
    assert r.returncode == 0 and json.loads(out.read_text())["alerts"] == []


def test_threshold_file_overrides_a_default(tmp_path):
    th = tmp_path / "t.toml"
    th.write_text("[alert]\ncost_per_prompt_session = 100.0\n")
    _, rep = report(tmp_path, "--thresholds", th)
    assert not any(a["metric"] == "m1" and "session" in a["text"] for a in rep["alerts"])
    _, base = report(tmp_path)
    assert any(a["metric"] == "m1" and "session" in a["text"] for a in base["alerts"])


def test_empty_window_reports_no_sessions_and_exits_zero(tmp_path):
    r, rep = report(tmp_path, transcripts=False, outcomes=FIX / "pr-outcomes.jsonl")
    assert r.returncode == 0 and rep["sessions"] == 0 and "no sessions" in r.stdout


def project_week(tmp_path, prs):
    rows = [{"session_id": f"s{i}", "ts_last": "2026-03-05T10:00:00Z", "project": "big",
             "turns": 10, "human_prompts": 10, "cost_usd": 100.0, "tool_calls": 100,
             "prs": [f"o/r#{i}"], "wall_seconds": 600} for i in range(prs)]
    rec = tmp_path / "rec.jsonl"
    rec.write_text("\n".join(map(json.dumps, rows)) + "\n")
    out_rows = [{"ref": "o/r#0", "state": "MERGED", "merged": "2026-03-05T12:00:00Z",
                 "hours_to_merge": 2.0, "review_rounds": 0}]
    outc = tmp_path / "out.jsonl"
    outc.write_text("\n".join(map(json.dumps, out_rows)) + "\n")
    out = tmp_path / "r.json"
    run_script("report.py", "--records", rec, "--outcomes", outc, *WINDOW, "--json", out)
    return json.loads(out.read_text())


def test_project_with_fewer_than_five_prs_does_not_alert_on_cost_per_merged_pr(tmp_path):
    rep = project_week(tmp_path, 4)  # $400 per merged PR, but only 4 PRs
    assert not any("cost per merged PR" in a["text"] for a in rep["alerts"])


def test_project_with_five_prs_alerts_on_cost_per_merged_pr(tmp_path):
    rep = project_week(tmp_path, 5)
    assert any("cost per merged PR" in a["text"] and "big" in a["text"] for a in rep["alerts"])


def test_changes_log_prints_delta_since_each_change_date(tmp_path):
    r, rep = report(tmp_path, "--changes", FIX / "changes.jsonl")
    ch = {c["rule"]: c for c in rep["changes"]}
    assert ch["R-sleep-hook"]["now"] == pytest.approx(6 / 205 * 100)
    assert ch["R-sleep-hook"]["delta"] == pytest.approx(6 / 205 * 100 - 80.0)
    assert ch["R-sleep-hook"]["no_op_candidate"] is False
    assert ch["R-noop"]["delta"] == 0 and ch["R-noop"]["no_op_candidate"] is True   # 26 days, no move
    assert ch["R-gate"]["no_op_candidate"] is False                                  # only 7 days old
    assert "R-noop" in r.stdout


def test_skill_hit_rate_splits_visible_and_name_only(tmp_path):
    def rec(i, invoked, visible):
        return {"session_id": f"k{i}", "ts_last": "2026-03-05T10:00:00Z", "project": "p",
                "turns": 1, "human_prompts": 1, "cost_usd": 1.0, "wall_seconds": 10,
                "skill_opportunities": ["a"], "skills_invoked": ["a"] if invoked else [],
                "skills_offered": {"visible": ["a"] if visible else [],
                                   "name_only": [] if visible else ["a"]}}
    rows = [rec(0, True, True), rec(1, False, True), rec(2, False, False), rec(3, False, False)]
    path = tmp_path / "k.jsonl"
    path.write_text("\n".join(map(json.dumps, rows)) + "\n")
    out = tmp_path / "r.json"
    run_script("report.py", "--records", path, *WINDOW, "--json", out)
    skill = json.loads(out.read_text())["metrics"]["m8"]["skills"]["a"]
    assert skill["visible"] == {"opportunities": 2, "invoked": 1, "rate": 0.5}
    assert skill["name_only"] == {"opportunities": 2, "invoked": 0, "rate": 0.0}


def test_records_file_keeps_the_last_line_per_session(tmp_path):
    rows = [{"session_id": "x", "ts_last": "2026-03-05T10:00:00Z", "turns": 1, "human_prompts": 1,
             "cost_usd": 1.0, "wall_seconds": 5},
            {"session_id": "x", "ts_last": "2026-03-05T10:00:00Z", "turns": 2, "human_prompts": 1,
             "cost_usd": 4.0, "wall_seconds": 5}]
    path = tmp_path / "l.jsonl"
    path.write_text("\n".join(map(json.dumps, rows)) + "\n")
    out = tmp_path / "r.json"
    run_script("report.py", "--records", path, *WINDOW, "--json", out)
    rep = json.loads(out.read_text())
    assert rep["sessions"] == 1 and rep["metrics"]["m1"]["value"] == pytest.approx(4.0)
