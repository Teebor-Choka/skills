"""metrics.py: the fixed `record` interface and the edge cases behind each metric."""
import json

import pytest

from helpers import asst_text, asst_tool, at, record_of, run_script, tool_result, user_text, write

KEYS = {"session_id", "ts_last", "project", "turns", "human_prompts", "compactions", "cost_usd",
        "context_tokens_peak", "tool_errors", "timer_turns", "outcome"}
SONNET = "claude-sonnet-4-5"


def u(n=1_000_000):
    return {"input_tokens": n, "output_tokens": 0}


def rows_at(rows):
    return [at(r, f"2026-04-01T10:{i // 60:02d}:{i % 60:02d}Z") for i, r in enumerate(rows)]


def test_record_is_one_json_line_with_exactly_the_fixed_keys(tmp_path):
    p = write(tmp_path, rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(10))]))
    r = run_script("metrics.py", "record", p)
    assert r.returncode == 0 and r.stdout.count("\n") == 1
    assert set(json.loads(r.stdout)) == KEYS


def test_unreadable_input_exits_zero_with_an_error_line(tmp_path):
    r = run_script("metrics.py", "record", tmp_path / "missing.jsonl")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert list(out) == ["error"] and out["error"]


def test_output_is_deterministic(tmp_path):
    p = write(tmp_path, rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(10))]))
    first, second = run_script("metrics.py", "record", p), run_script("metrics.py", "record", p)
    assert first.returncode == 0 and first.stdout and first.stdout == second.stdout


def test_transcript_is_not_modified(tmp_path):
    p = write(tmp_path, rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(10))]))
    before = open(p).read()
    record_of(p)
    assert open(p).read() == before


def test_queued_notification_and_peer_messages_are_not_human_prompts(tmp_path):
    rows = rows_at([
        user_text("real prompt"),
        asst_text("a", "m1", SONNET, u(10)),
        user_text("<task-notification><task-id>t</task-id></task-notification>"),
        user_text("<cross-session-message>hello</cross-session-message>"),
        {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "queued text"}},
    ])
    assert record_of(write(tmp_path, rows))["human_prompts"] == 1


def test_repeated_message_id_counts_one_turn(tmp_path):
    rows = rows_at([user_text("hi")] + [asst_text("x", "m1", SONNET, u(10))] * 3)
    assert record_of(write(tmp_path, rows))["turns"] == 1


def test_last_cost_state_wins_within_a_segment(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(10))]
                   + [{"type": "cost-state", "totalCostUsd": v} for v in (1.0, 4.0, 6.0)])
    assert record_of(write(tmp_path, rows))["cost_usd"] == pytest.approx(6.0)


def test_session_without_cost_state_is_priced_from_tokens_and_flagged(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u())])
    full = record_of(write(tmp_path, rows), full=True)
    assert full["cost_usd"] == pytest.approx(3.0) and full["cost_source"] == "usage"


def test_unknown_model_without_cost_state_is_unpriced(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", "mystery-1", u())])
    full = record_of(write(tmp_path, rows), full=True)
    assert full["cost_usd"] is None and full["unpriced"] is True


def test_zero_cost_over_fifty_turns_is_unpriced(tmp_path):
    rows = [user_text("hi")] + [asst_text("x", f"m{i}", SONNET, {}) for i in range(51)]
    rows.append({"type": "cost-state", "totalCostUsd": 0})
    full = record_of(write(tmp_path, rows_at(rows)), full=True)
    assert full["unpriced"] is True and full["cost_usd"] is None


def test_a_session_does_not_read_its_subagent_files(tmp_path):
    main = write(tmp_path, rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(10)),
                                    {"type": "cost-state", "totalCostUsd": 2.0}]), name="s.jsonl")
    (tmp_path / "s" / "subagents").mkdir(parents=True)
    write(tmp_path / "s" / "subagents", [{"type": "cost-state", "totalCostUsd": 9.0}], "agent-1.jsonl")
    assert record_of(main)["cost_usd"] == pytest.approx(2.0)


def test_tool_error_counts_flagged_results_per_call(tmp_path):
    rows = rows_at([
        user_text("hi"),
        asst_tool("Bash", {"command": "a"}, "m1", "t1", SONNET, u(1)),
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                                  "is_error": True, "content": "x"}]}},
        asst_tool("Bash", {"command": "b"}, "m2", "t2", SONNET, u(1)),
        tool_result("fine, but says error: in prose", "t2"),
    ])
    full = record_of(write(tmp_path, rows), full=True)
    assert (full["tool_calls"], full["tool_errors"]) == (2, 1)


def test_denial_and_interrupt_are_counted_and_not_prompts(tmp_path):
    rows = rows_at([
        user_text("hi"),
        asst_tool("Bash", {"command": "a"}, "m1", "t1", SONNET, u(1)),
        {"type": "user", "message": {"content": [{
            "type": "tool_result", "tool_use_id": "t1", "is_error": True,
            "content": "The user doesn't want to proceed with this tool use."}]}},
        user_text("[Request interrupted by user for tool use]"),
    ])
    full = record_of(write(tmp_path, rows), full=True)
    assert (full["denials"], full["interrupts"], full["human_prompts"]) == (1, 1, 1)


def test_correction_wording_is_not_counted(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(1)),
                    user_text("no, don't do that instead"), asst_text("y", "m2", SONNET, u(1))])
    full = record_of(write(tmp_path, rows), full=True)
    assert (full["interrupts"], full["denials"], full["nudges"]) == (0, 0, 0)


def test_bare_continue_variants_are_nudges(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u(1)), user_text("Continue."),
                    user_text("keep going"), user_text("continue the refactor of the parser")])
    assert record_of(write(tmp_path, rows), full=True)["nudges"] == 2


def test_wait_under_thirty_minutes_is_not_a_wait(tmp_path):
    rows = [at(user_text("hi"), "2026-04-01T10:00:00Z"),
            at(asst_text("x", "m1", SONNET, u(1)), "2026-04-01T10:00:10Z"),
            at(user_text("again"), "2026-04-01T10:29:00Z")]
    assert record_of(write(tmp_path, rows), full=True)["waits"] == []


def test_timer_turn_follows_a_timer_tool_result_or_a_notification_only(tmp_path):
    rows = rows_at([
        user_text("go"),
        asst_tool("ScheduleWakeup", {}, "m1", "t1", SONNET, u(1)),
        tool_result("scheduled", "t1"),
        asst_text("woke", "m2", SONNET, u(1)),        # timer turn
        asst_text("second turn of the same wake", "m3", SONNET, u(1)),  # not
        user_text("human again"),
        asst_text("reply", "m4", SONNET, u(1)),       # not
    ])
    assert record_of(write(tmp_path, rows))["timer_turns"] == 1


def test_timer_turn_in_a_big_context_is_flagged(tmp_path):
    rows = rows_at([
        user_text("go"),
        asst_tool("Monitor", {}, "m1", "t1", SONNET, {"input_tokens": 300_000}),
        tool_result("tick", "t1"),
        asst_text("woke", "m2", SONNET, {"input_tokens": 310_000}),
    ])
    assert record_of(write(tmp_path, rows), full=True)["timer_turns_big_context"] == 1


def test_session_id_and_project_fall_back_to_file_and_folder(tmp_path):
    p = write(tmp_path, rows_at([user_text("hi")]), name="abc-123.jsonl")
    r = record_of(p)
    assert r["session_id"] == "abc-123" and r["project"] == tmp_path.name


def test_dispatch_table_marks_opportunities_and_invocations(tmp_path):
    table = tmp_path / "dispatch.json"
    table.write_text(json.dumps({"alpha": ["\\brelease\\b"], "beta": ["\\bnever\\b"]}))
    rows = rows_at([
        {"type": "attachment", "attachment": {"type": "skill_listing",
                                              "content": "- alpha: do a\n- beta"}},
        user_text("cut a release"),
        asst_tool("Skill", {"skill": "alpha"}, "m1", "t1", SONNET, u(1)),
    ])
    r = run_script("metrics.py", "full", write(tmp_path, rows), "--dispatch", table)
    full = json.loads(r.stdout)
    assert full["skill_opportunities"] == ["alpha"] and full["skills_invoked"] == ["alpha"]
    assert full["skills_offered"] == {"visible": ["alpha"], "name_only": ["beta"]}


def test_synthetic_model_entries_do_not_make_a_session_unpriced(tmp_path):
    rows = rows_at([user_text("hi"), asst_text("x", "m1", SONNET, u()),
                    asst_text("x", "m2", "<synthetic>", u(5))])
    full = record_of(write(tmp_path, rows), full=True)
    assert full["unpriced"] is False and full["cost_usd"] == pytest.approx(3.0)


def test_skill_listings_sent_in_pieces_are_merged(tmp_path):
    def listing(text):
        return {"type": "attachment", "attachment": {"type": "skill_listing", "content": text}}
    rows = rows_at([listing("- alpha: a"), listing("- beta"), user_text("hi")])
    offered = record_of(write(tmp_path, rows), full=True)["skills_offered"]
    assert offered == {"visible": ["alpha"], "name_only": ["beta"]}
