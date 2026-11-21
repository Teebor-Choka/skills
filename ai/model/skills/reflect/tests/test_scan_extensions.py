"""Tests for the scan-sessions.py additions: event-time windows, turns, outcomes, hooks."""
import json
import sys

import pytest

from helpers import (asst_text, asst_tool, at, load, tool_result, user_text, write)

scan = load("scan-sessions.py")

OLD, NEW = "2026-01-05T10:00:00Z", "2026-03-04T10:00:00Z"


def two_period_rows():
    return [at(asst_tool("Bash", {"command": "a"}, use_id="u1"), OLD),
            at(tool_result("error: old failure", "u1"), OLD),
            at(asst_tool("Bash", {"command": "b"}, use_id="u2"), NEW),
            at(tool_result("error: new failure", "u2"), NEW)]


# --- RF-01: event time, not file mtime --------------------------------------

def test_window_counts_only_events_inside_it(tmp_path):
    path = write(tmp_path, two_period_rows())
    r = scan.score_session(path, since=scan.parse_date("2026-02-01"))
    assert r["signals"]["errors"] == 1
    assert r["in_window"]["share"] == 0.5


def test_session_modified_today_with_old_events_is_outside_the_window(tmp_path, monkeypatch):
    write(tmp_path, [at(r, OLD) for r in two_period_rows()])  # fresh mtime, old events
    monkeypatch.setattr(sys, "argv", ["scan", str(tmp_path), "--since", "2026-02-01", "--json"])
    assert scan.main() == 1


def test_session_with_old_mtime_but_events_in_window_is_kept(tmp_path, monkeypatch, capsys):
    import os
    p = write(tmp_path, [at(r, NEW) for r in two_period_rows()])
    os.utime(p, (1_000_000_000, 1_000_000_000))  # file mtime in 2001
    monkeypatch.setattr(sys, "argv", ["scan", str(tmp_path), "--since", "2026-02-01", "--json"])
    assert scan.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["signals"]["errors"] == 2
    assert out[0]["in_window"]["share"] == 1.0


# --- RF-03: turns are unique message ids -------------------------------------

def test_turns_count_unique_message_ids_not_content_block_lines(tmp_path):
    rows = [asst_text("a", msg_id="m1"), asst_tool("Read", {"file_path": "/a"}, msg_id="m1"),
            asst_tool("Read", {"file_path": "/b"}, msg_id="m1"), asst_text("b", msg_id="m2")]
    assert scan.score_session(write(tmp_path, rows))["signals"]["turns"] == 2


# --- RF-04: first and last seen, weekly series ---------------------------------

def test_first_last_seen_and_weekly_series(tmp_path):
    rows = [at(asst_tool("Bash", {"command": "a"}, use_id="u1"), "2026-03-04T10:00:00Z"),
            at(tool_result("error: x", "u1"), "2026-03-04T10:00:01Z"),
            at(asst_tool("Bash", {"command": "b"}, use_id="u2"), "2026-03-11T09:00:00Z"),
            at(tool_result("error: y", "u2"), "2026-03-11T09:00:01Z")]
    r = scan.score_session(write(tmp_path, rows))
    assert r["first_seen"] == "2026-03-04T10:00:00Z"
    assert r["last_seen"] == "2026-03-11T09:00:01Z"
    assert r["weekly"] == {"2026-W10": {"errors": 1}, "2026-W11": {"errors": 1}}
    assert all(m["ts"] for m in r["moments"])


# --- RF-06 inside the scanner: injected turns are not human --------------------

def test_a_skill_body_and_compaction_summary_are_not_steering(tmp_path):
    rows = [asst_text("go"),
            user_text("Base directory for this skill: /x\ninstead do not stop", isMeta=True),
            user_text("This session is being continued from a previous conversation. "
                      "revert everything"),
            user_text("fix the title")]
    r = scan.score_session(write(tmp_path, rows))
    assert r["signals"]["corrections"] == 0
    assert r["signals"]["steers"] == 1


# --- RF-07: per-tool counts -------------------------------------------------

def test_tool_counts_per_transcript(tmp_path):
    rows = [asst_tool("Bash", {"command": "a"}, use_id="1"),
            asst_tool("Bash", {"command": "b"}, use_id="2"),
            asst_tool("Read", {"file_path": "/a"}, use_id="3")]
    assert scan.score_session(write(tmp_path, rows))["tools"] == {"Bash": 2, "Read": 1}


# --- RF-08 inside the scanner -----------------------------------------------------

def test_excerpts_never_carry_a_short_password(tmp_path):
    rows = [asst_tool("Bash", {"command": "run"}, use_id="1"),
            tool_result("error: login failed password=hunter2", "1")]
    r = scan.score_session(write(tmp_path, rows))
    assert "hunter2" not in json.dumps(r)


def test_output_of_a_secret_printing_command_is_not_excerpted(tmp_path):
    rows = [asst_tool("Bash", {"command": "cat ~/.config/app/token"}, use_id="1"),
            tool_result("error: bad value zzTopSecretValue", "1")]
    assert "zzTopSecretValue" not in json.dumps(scan.score_session(write(tmp_path, rows)))


# --- RF-05 inside the scanner: hook outcomes ----------------------------------------

def test_hook_events_split_into_deny_nonblocking_and_context(tmp_path):
    def hook(kind, **kw):
        return {"type": "attachment", "attachment": {"type": kind, "hookName": "gate.sh", **kw}}
    rows = [hook("hook_blocking_error", exitCode=2), hook("hook_non_blocking_error", exitCode=1),
            hook("hook_non_blocking_error", exitCode=1), hook("hook_additional_context",
                                                              content=["x"])]
    run = scan.score_run("k", [write(tmp_path, rows)])
    assert run["hooks"] == {"gate.sh": {"deny": 1, "nonblocking": 2, "context": 1}}


def hook_deny_result(text, use_id):
    row = tool_result(text, use_id)
    row["message"]["content"][0]["is_error"] = True
    return row


def test_hook_denial_in_a_tool_result_counts_as_a_deny_for_that_hook(tmp_path):
    rows = [asst_tool("Bash", {"command": "git add ."}, use_id="u1"),
            hook_deny_result("PreToolUse:Bash hook error: git-guard: stage explicit paths", "u1"),
            asst_tool("Edit", {"file_path": "a"}, use_id="u2"),
            hook_deny_result("PreToolUse:Edit hook error: load the skill first", "u2"),
            {"type": "attachment", "attachment": {"type": "hook_non_blocking_error",
                                                  "hookName": "PreToolUse:Bash", "exitCode": 1}}]
    run = scan.score_run("k", [write(tmp_path, rows)])
    assert run["hooks"]["PreToolUse:Bash"] == {"deny": 1, "nonblocking": 1, "context": 0}
    assert run["hooks"]["PreToolUse:Edit"]["deny"] == 1


def test_hook_error_text_inside_other_output_is_not_a_denial(tmp_path):
    rows = [asst_tool("Bash", {"command": "cat notes"}, use_id="u1"),
            tool_result("notes: PreToolUse:Bash hook error: quoted in a file", "u1")]
    assert scan.score_run("k", [write(tmp_path, rows)])["hooks"] == {}


# --- RF-11: outcomes and the human-as-loop signal -------------------------------------

def outcome(tmp_path, rows):
    return scan.score_run("k", [write(tmp_path, rows)])["outcome"]["label"]


def test_outcome_artifact_when_a_pr_link_exists(tmp_path):
    rows = [user_text("go"), asst_text("done"),
            {"type": "pr-link", "prUrl": "https://github.com/o/r/pull/1"}]
    assert outcome(tmp_path, rows) == "artifact"


def test_outcome_evidence_when_the_final_message_has_a_url_or_verification(tmp_path):
    assert outcome(tmp_path, [user_text("go"), asst_text("see https://example.org/x")]) == "evidence"
    assert outcome(tmp_path, [user_text("go"), asst_text("Verified: 12 passed")]) == "evidence"


def test_outcome_abandoned_when_the_last_turn_is_human(tmp_path):
    rows = [user_text("start"), asst_text("working"), user_text("why so slow")]
    assert outcome(tmp_path, rows) == "abandoned"


def test_outcome_none_when_the_agent_ends_without_evidence(tmp_path):
    assert outcome(tmp_path, [user_text("go"), asst_text("ok")]) == "none"


def test_human_as_loop_counts_short_human_messages(tmp_path):
    rows = [user_text("implement the parser for the new config format please"),
            asst_text("a"), user_text("continue"), asst_text("b"), user_text("yes go ahead"),
            asst_text("c"), user_text("<system-reminder>ok</system-reminder>")]
    run = scan.score_run("k", [write(tmp_path, rows)])
    assert run["outcome"]["human_loop"] == 2


def test_outcome_summary_compares_friction_by_label():
    runs = [{"score": 10.0, "outcome": {"label": "artifact"}},
            {"score": 30.0, "outcome": {"label": "artifact"}},
            {"score": 90.0, "outcome": {"label": "abandoned"}}]
    assert scan.outcome_summary(runs) == {
        "artifact": {"runs": 2, "mean_score": 20.0},
        "abandoned": {"runs": 1, "mean_score": 90.0}}


# --- RF-15: long-session share on both bases --------------------------------------------

def test_long_session_share_reports_sessions_and_turn_bases():
    runs = [{"signals": {"turns": 300}}, {"signals": {"turns": 10}},
            {"signals": {"turns": 10}}, {"signals": {"turns": 20}}]
    share = scan.long_session_share(runs, long_turns=200)
    assert share == {"by_sessions": 0.25, "by_turns": 0.88, "long_turns": 200}
